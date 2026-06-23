export type TimeSlot = {
  opensAt: string;
  closesAt: string;
};

export type BusinessDayHours = {
  day: string;
  isOpen: boolean;
  slots: TimeSlot[];
};

const DAYS = [
  "Monday",
  "Tuesday",
  "Wednesday",
  "Thursday",
  "Friday",
  "Saturday",
  "Sunday",
] as const;

const STANDARD_SLOT: TimeSlot = { opensAt: "09:00", closesAt: "22:00" };
const EVENING_SLOT: TimeSlot = { opensAt: "19:00", closesAt: "23:00" };

export function formatTimeLabel(value: string): string {
  const [hourText, minute] = value.split(":");
  const hour = Number(hourText);
  if (!minute || Number.isNaN(hour)) return value;

  const displayHour = hour % 12 || 12;
  const period = hour < 12 ? "AM" : "PM";
  return `${String(displayHour).padStart(2, "0")}:${minute} ${period}`;
}

export const TIME_OPTIONS = Array.from({ length: 48 }, (_, index) => {
  const hour = Math.floor(index / 2);
  const minute = index % 2 === 0 ? "00" : "30";
  const value = `${String(hour).padStart(2, "0")}:${minute}`;
  return { value, label: formatTimeLabel(value) };
});

function cloneSlots(slots: TimeSlot[]): TimeSlot[] {
  return slots.map((slot) => ({ ...slot }));
}

export function createDefaultBusinessHours(): BusinessDayHours[] {
  return DAYS.map((day, index) => ({
    day,
    isOpen: index < 5,
    slots:
      index === 2
        ? [
            { opensAt: "09:00", closesAt: "12:00" },
            { ...EVENING_SLOT },
          ]
        : [{ ...STANDARD_SLOT }],
  }));
}

export function setDayOpen(
  schedule: BusinessDayHours[],
  dayIndex: number,
  isOpen: boolean,
): BusinessDayHours[] {
  return schedule.map((day, index) =>
    index === dayIndex ? { ...day, isOpen } : day,
  );
}

export function addTimeSlot(
  schedule: BusinessDayHours[],
  dayIndex: number,
): BusinessDayHours[] {
  return schedule.map((day, index) => {
    if (index !== dayIndex || day.slots.length >= 2) return day;
    return { ...day, slots: [...day.slots, { ...EVENING_SLOT }] };
  });
}

export function removeTimeSlot(
  schedule: BusinessDayHours[],
  dayIndex: number,
  slotIndex: number,
): BusinessDayHours[] {
  return schedule.map((day, index) => {
    if (index !== dayIndex || day.slots.length === 1) return day;
    return {
      ...day,
      slots: day.slots.filter((_, indexToKeep) => indexToKeep !== slotIndex),
    };
  });
}

export function applyMondayHours(
  schedule: BusinessDayHours[],
): BusinessDayHours[] {
  const monday = schedule[0];
  return schedule.map((day) => ({
    ...day,
    isOpen: monday.isOpen,
    slots: cloneSlots(monday.slots),
  }));
}

export function markWeekendClosed(
  schedule: BusinessDayHours[],
): BusinessDayHours[] {
  return schedule.map((day, index) =>
    index >= 5 ? { ...day, isOpen: false } : day,
  );
}

export function updateTimeSlot(
  schedule: BusinessDayHours[],
  dayIndex: number,
  slotIndex: number,
  field: keyof TimeSlot,
  value: string,
): BusinessDayHours[] {
  return schedule.map((day, index) => {
    if (index !== dayIndex) return day;
    return {
      ...day,
      slots: day.slots.map((slot, currentSlotIndex) =>
        currentSlotIndex === slotIndex ? { ...slot, [field]: value } : slot,
      ),
    };
  });
}

export function isTimeSlotValid(slot: TimeSlot): boolean {
  return (
    Boolean(slot.opensAt) &&
    Boolean(slot.closesAt) &&
    slot.opensAt !== slot.closesAt
  );
}

export function isOvernightSlot(slot: TimeSlot): boolean {
  return isTimeSlotValid(slot) && slot.closesAt < slot.opensAt;
}

export function isBusinessHoursValid(schedule: BusinessDayHours[]): boolean {
  return schedule.every(
    (day) =>
      !day.isOpen ||
      (day.slots.length > 0 && day.slots.every(isTimeSlotValid)),
  );
}
