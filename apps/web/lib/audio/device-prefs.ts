/**
 * Task 4.4's Settings > Audio page: input/output device selection. Device ids are meaningful
 * only on the browser/machine that enumerated them, so — unlike echo-cancellation/noise-
 * suppression/speaking-rate/captions, which are real account preferences persisted server-side
 * on the profile — these live in localStorage only, read by both the settings page (to persist
 * a choice) and the practice room (to apply it when starting capture).
 */

const INPUT_DEVICE_KEY = "interactai-audio-input-device-id";
const OUTPUT_DEVICE_KEY = "interactai-audio-output-device-id";

function readLocalStorage(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

function writeLocalStorage(key: string, value: string): void {
  try {
    localStorage.setItem(key, value);
  } catch {
    // Private browsing / storage disabled — the preference just doesn't persist this session.
  }
}

export function getSavedInputDeviceId(): string | null {
  return readLocalStorage(INPUT_DEVICE_KEY);
}

export function setSavedInputDeviceId(deviceId: string): void {
  writeLocalStorage(INPUT_DEVICE_KEY, deviceId);
}

export function getSavedOutputDeviceId(): string | null {
  return readLocalStorage(OUTPUT_DEVICE_KEY);
}

export function setSavedOutputDeviceId(deviceId: string): void {
  writeLocalStorage(OUTPUT_DEVICE_KEY, deviceId);
}
