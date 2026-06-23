import { apiUrl } from "@/lib/api";
import { ApiError } from "@/lib/auth";

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

// --------------------------------------------------------------------------- //
// Backend mapping + persistence
//
// IMPORTANT: the frontend DAYS array is 0=Monday..6=Sunday, but the backend
// `business_hours.day_of_week` is 0=Sunday..6=Saturday. Always remap.
// --------------------------------------------------------------------------- //
export type BusinessHoursItem = {
  day_of_week: number;
  open_time: string | null;
  close_time: string | null;
  is_closed: boolean;
};

export type BusinessHoursPayload = { hours: BusinessHoursItem[] };

type Fetcher = typeof fetch;

export function webIndexToBackendDow(index: number): number {
  return (index + 1) % 7; // Mon(0)->1, ... Sat(5)->6, Sun(6)->0
}

export function backendDowToWebIndex(dow: number): number {
  return (dow + 6) % 7; // Sun(0)->6, Mon(1)->0, ... Sat(6)->5
}

function trimTime(value: string): string {
  // Backend serializes time as "HH:MM:SS"; the UI selects use "HH:MM".
  return value.slice(0, 5);
}

export function toBusinessHoursPayload(
  schedule: BusinessDayHours[],
): BusinessHoursPayload {
  const hours = schedule.map((day, index) => {
    const day_of_week = webIndexToBackendDow(index);
    if (!day.isOpen || day.slots.length === 0) {
      return { day_of_week, open_time: null, close_time: null, is_closed: true };
    }
    // The backend stores ONE window per day (UNIQUE business_id, day_of_week), so
    // collapse multiple slots to an envelope (earliest open .. latest close).
    // Split shifts are not representable yet.
    return {
      day_of_week,
      open_time: day.slots[0].opensAt,
      close_time: day.slots[day.slots.length - 1].closesAt,
      is_closed: false,
    };
  });
  return { hours };
}

export function scheduleFromHours(rows: BusinessHoursItem[]): BusinessDayHours[] {
  const byWebIndex = new Map<number, BusinessHoursItem>();
  for (const row of rows) byWebIndex.set(backendDowToWebIndex(row.day_of_week), row);

  return createDefaultBusinessHours().map((day, index) => {
    const row = byWebIndex.get(index);
    if (!row) return day; // no saved row: keep the editable default
    if (row.is_closed || !row.open_time || !row.close_time) {
      return { ...day, isOpen: false };
    }
    return {
      ...day,
      isOpen: true,
      slots: [{ opensAt: trimTime(row.open_time), closesAt: trimTime(row.close_time) }],
    };
  });
}

async function hoursRequest<T>({
  path,
  accessToken,
  method = "GET",
  body,
  fetcher = fetch,
}: {
  path: string;
  accessToken: string;
  method?: "GET" | "PUT" | "PATCH";
  body?: unknown;
  fetcher?: Fetcher;
}): Promise<T> {
  let response: Response;
  try {
    response = await fetcher(apiUrl(path), {
      method,
      headers: {
        Authorization: `Bearer ${accessToken}`,
        ...(body === undefined ? {} : { "Content-Type": "application/json" }),
      },
      ...(body === undefined ? {} : { body: JSON.stringify(body) }),
    });
  } catch {
    throw new ApiError(
      "Couldn't reach the server. Is the API running on http://localhost:8000?",
      0,
    );
  }

  if (!response.ok) {
    let message = "Couldn't save your opening hours. Please try again.";
    let code: string | undefined;
    try {
      const payload = (await response.json()) as {
        error?: { message?: string; code?: string };
      };
      message = payload.error?.message ?? message;
      code = payload.error?.code;
    } catch {
      // Keep the stable fallback for non-JSON responses.
    }
    throw new ApiError(message, response.status, code);
  }

  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export function listBusinessHours({
  accessToken,
  businessId,
  fetcher = fetch,
}: {
  accessToken: string;
  businessId: string;
  fetcher?: Fetcher;
}): Promise<BusinessHoursItem[]> {
  return hoursRequest<BusinessHoursItem[]>({
    path: `/businesses/${businessId}/hours`,
    accessToken,
    fetcher,
  });
}

export async function saveBusinessHours({
  accessToken,
  businessId,
  schedule,
  acceptingOrders,
  fetcher = fetch,
}: {
  accessToken: string;
  businessId: string;
  schedule: BusinessDayHours[];
  acceptingOrders: boolean;
  fetcher?: Fetcher;
}): Promise<void> {
  await Promise.all([
    hoursRequest({
      path: `/businesses/${businessId}/hours`,
      accessToken,
      method: "PUT",
      body: toBusinessHoursPayload(schedule),
      fetcher,
    }),
    // The "Accepting orders now" toggle lives on this screen but maps to the business.
    hoursRequest({
      path: `/businesses/${businessId}`,
      accessToken,
      method: "PATCH",
      body: { accepting_orders: acceptingOrders },
      fetcher,
    }),
  ]);
}
