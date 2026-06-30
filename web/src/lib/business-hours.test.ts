import { describe, expect, it } from "vitest";

import {
  addTimeSlot,
  applyMondayHours,
  backendDowToWebIndex,
  createDefaultBusinessHours,
  formatTimeLabel,
  isBusinessHoursValid,
  isOvernightSlot,
  isTimeSlotValid,
  markWeekendClosed,
  removeTimeSlot,
  scheduleFromHours,
  setDayOpen,
  TIME_OPTIONS,
  toBusinessHoursPayload,
  updateTimeSlot,
  webIndexToBackendDow,
} from "@/lib/business-hours";

describe("business hours schedule", () => {
  it("provides half-hour dropdown options with readable 12-hour labels", () => {
    expect(TIME_OPTIONS).toHaveLength(48);
    expect(TIME_OPTIONS[0]).toEqual({ value: "00:00", label: "12:00 AM" });
    expect(TIME_OPTIONS.at(-1)).toEqual({ value: "23:30", label: "11:30 PM" });
    expect(formatTimeLabel("09:30")).toBe("09:30 AM");
    expect(formatTimeLabel("22:00")).toBe("10:00 PM");
  });

  it("starts with the screenshot schedule", () => {
    const schedule = createDefaultBusinessHours();

    expect(schedule).toHaveLength(7);
    expect(schedule.slice(0, 5).every((day) => day.isOpen)).toBe(true);
    expect(schedule.slice(5).every((day) => !day.isOpen)).toBe(true);
    expect(schedule[2].slots).toEqual([
      { opensAt: "09:00", closesAt: "12:00" },
      { opensAt: "19:00", closesAt: "23:00" },
    ]);
  });

  it("applies Monday's hours to every day without sharing slot references", () => {
    const schedule = applyMondayHours(createDefaultBusinessHours());

    expect(schedule.every((day) => day.isOpen)).toBe(true);
    expect(
      schedule.every(
        (day) =>
          day.slots.length === 1 &&
          day.slots[0].opensAt === "09:00" &&
          day.slots[0].closesAt === "22:00",
      ),
    ).toBe(true);
    expect(schedule[0].slots).not.toBe(schedule[1].slots);
  });

  it("marks Saturday and Sunday closed while preserving weekday hours", () => {
    const schedule = applyMondayHours(createDefaultBusinessHours());
    const closedWeekend = markWeekendClosed(schedule);

    expect(closedWeekend.slice(0, 5).every((day) => day.isOpen)).toBe(true);
    expect(closedWeekend.slice(5).every((day) => !day.isOpen)).toBe(true);
  });

  it("supports toggling days and adding or removing a second time slot", () => {
    let schedule = createDefaultBusinessHours();

    schedule = setDayOpen(schedule, 5, true);
    schedule = addTimeSlot(schedule, 5);
    schedule = addTimeSlot(schedule, 5);
    expect(schedule[5]).toMatchObject({ isOpen: true });
    expect(schedule[5].slots).toHaveLength(2);

    schedule = removeTimeSlot(schedule, 5, 1);
    expect(schedule[5].slots).toHaveLength(1);
  });

  it("updates one field without mutating the rest of the schedule", () => {
    const schedule = createDefaultBusinessHours();
    const updated = updateTimeSlot(schedule, 0, 0, "opensAt", "10:30");

    expect(updated[0].slots[0].opensAt).toBe("10:30");
    expect(schedule[0].slots[0].opensAt).toBe("09:00");
    expect(updated[1]).toBe(schedule[1]);
  });

  it("accepts a closing time on the following day", () => {
    const schedule = createDefaultBusinessHours();
    const overnight = schedule.map((day, index) =>
      index === 0
        ? { ...day, slots: [{ opensAt: "14:00", closesAt: "00:00" }] }
        : day,
    );

    expect(isTimeSlotValid(overnight[0].slots[0])).toBe(true);
    expect(isOvernightSlot(overnight[0].slots[0])).toBe(true);
    expect(isBusinessHoursValid(overnight)).toBe(true);
  });

  it("rejects an open slot with identical start and end times", () => {
    const schedule = createDefaultBusinessHours().map((day, index) =>
      index === 0
        ? { ...day, slots: [{ opensAt: "14:00", closesAt: "14:00" }] }
        : day,
    );

    expect(isTimeSlotValid(schedule[0].slots[0])).toBe(false);
    expect(isOvernightSlot(schedule[0].slots[0])).toBe(false);
    expect(isBusinessHoursValid(schedule)).toBe(false);
  });
});

describe("backend hours mapping", () => {
  it("remaps Mon=0..Sun=6 (frontend) to Sun=0..Sat=6 (backend)", () => {
    expect(webIndexToBackendDow(0)).toBe(1); // Monday
    expect(webIndexToBackendDow(5)).toBe(6); // Saturday
    expect(webIndexToBackendDow(6)).toBe(0); // Sunday
    // round-trip
    for (let i = 0; i < 7; i += 1) {
      expect(backendDowToWebIndex(webIndexToBackendDow(i))).toBe(i);
    }
  });

  it("builds a 7-day payload with weekend (Sat/Sun) closed on the right backend days", () => {
    const schedule = markWeekendClosed(applyMondayHours(createDefaultBusinessHours()));
    const { hours } = toBusinessHoursPayload(schedule);

    expect(hours).toHaveLength(7);
    const byDow = new Map(hours.map((h) => [h.day_of_week, h]));
    // Saturday -> backend 6, Sunday -> backend 0 are closed.
    expect(byDow.get(6)?.is_closed).toBe(true);
    expect(byDow.get(0)?.is_closed).toBe(true);
    // Monday (backend 1) open with Monday's window.
    expect(byDow.get(1)).toMatchObject({
      is_closed: false,
      open_time: "09:00",
      close_time: "22:00",
    });
  });

  it("collapses a split-shift day to an envelope (earliest open .. latest close)", () => {
    // Default Wednesday (web index 2) has 09:00-12:00 and 19:00-23:00.
    const { hours } = toBusinessHoursPayload(createDefaultBusinessHours());
    const wednesday = hours.find((h) => h.day_of_week === webIndexToBackendDow(2));
    expect(wednesday).toMatchObject({ open_time: "09:00", close_time: "23:00" });
  });

  it("rebuilds the schedule from backend rows, trimming HH:MM:SS and honoring dow", () => {
    const schedule = scheduleFromHours([
      { day_of_week: 1, open_time: "10:00:00", close_time: "23:30:00", is_closed: false }, // Mon
      { day_of_week: 0, open_time: null, close_time: null, is_closed: true }, // Sun
    ]);
    expect(schedule[0]).toMatchObject({
      day: "Monday",
      isOpen: true,
      slots: [{ opensAt: "10:00", closesAt: "23:30" }],
    });
    expect(schedule[6]).toMatchObject({ day: "Sunday", isOpen: false });
  });
});
