// Interim local persistence for onboarding logo/cover images.
//
// There is no image-upload backend yet (the business only has `logo_url` /
// `cover_url` text columns), so a freshly picked image would otherwise live
// only in an ephemeral `blob:` object URL that dies on reload. Here we keep the
// selected File in IndexedDB, keyed per slot, and restore it as a preview when
// the user returns to the step. This is a stopgap to be removed once a real
// upload endpoint exists. Scope: one onboarding business per browser — slots are
// not namespaced by business id.

const DB_NAME = "orderly";
const DB_VERSION = 1;
const STORE = "onboarding-images";

export type ImageSlot = "logo" | "cover";

function openDb(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, DB_VERSION);
    request.onupgradeneeded = () => {
      const db = request.result;
      if (!db.objectStoreNames.contains(STORE)) {
        db.createObjectStore(STORE);
      }
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

/** Persist a picked image for the given slot. No-ops if IndexedDB is unavailable. */
export async function saveOnboardingImage(
  slot: ImageSlot,
  file: Blob,
): Promise<void> {
  if (typeof indexedDB === "undefined") return;
  const db = await openDb();
  try {
    await new Promise<void>((resolve, reject) => {
      const tx = db.transaction(STORE, "readwrite");
      tx.objectStore(STORE).put(file, slot);
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error);
      tx.onabort = () => reject(tx.error);
    });
  } finally {
    db.close();
  }
}

/** Load a previously persisted image for the given slot, or null. */
export async function loadOnboardingImage(slot: ImageSlot): Promise<Blob | null> {
  if (typeof indexedDB === "undefined") return null;
  const db = await openDb();
  try {
    return await new Promise<Blob | null>((resolve, reject) => {
      const tx = db.transaction(STORE, "readonly");
      const request = tx.objectStore(STORE).get(slot);
      request.onsuccess = () => resolve((request.result as Blob) ?? null);
      request.onerror = () => reject(request.error);
    });
  } finally {
    db.close();
  }
}
