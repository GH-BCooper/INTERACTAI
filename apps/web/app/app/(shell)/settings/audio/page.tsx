"use client";

import { useEffect, useState } from "react";

import { AudioCheckPanel } from "@/components/settings/audio-check-panel";
import { Button } from "@/components/ui/button";
import { useMe, useUpdateProfile } from "@/lib/api/hooks";
import {
  getSavedInputDeviceId,
  getSavedOutputDeviceId,
  setSavedInputDeviceId,
  setSavedOutputDeviceId,
} from "@/lib/audio/device-prefs";

function useDeviceList(kind: "audioinput" | "audiooutput") {
  const [devices, setDevices] = useState<MediaDeviceInfo[]>([]);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      if (typeof navigator === "undefined" || !navigator.mediaDevices?.enumerateDevices) return;
      const all = await navigator.mediaDevices.enumerateDevices();
      if (!cancelled) setDevices(all.filter((d) => d.kind === kind));
    }
    void load();
    navigator.mediaDevices?.addEventListener?.("devicechange", load);
    return () => {
      cancelled = true;
      navigator.mediaDevices?.removeEventListener?.("devicechange", load);
    };
  }, [kind]);

  return devices;
}

export default function AudioSettingsPage() {
  const { data: me } = useMe();
  const updateProfile = useUpdateProfile();

  const inputDevices = useDeviceList("audioinput");
  const outputDevices = useDeviceList("audiooutput");
  const [inputDeviceId, setInputDeviceId] = useState<string>("");
  const [outputDeviceId, setOutputDeviceId] = useState<string>("");

  const [captionsDefault, setCaptionsDefault] = useState(true);
  const [speakingRate, setSpeakingRate] = useState(1.0);
  const [echoCancellation, setEchoCancellation] = useState(true);
  const [noiseSuppression, setNoiseSuppression] = useState(true);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    setInputDeviceId(getSavedInputDeviceId() ?? "");
    setOutputDeviceId(getSavedOutputDeviceId() ?? "");
  }, []);

  useEffect(() => {
    if (me?.profile) {
      setCaptionsDefault(me.profile.captions_default);
      setSpeakingRate(me.profile.speaking_rate);
      setEchoCancellation(me.profile.echo_cancellation);
      setNoiseSuppression(me.profile.noise_suppression);
    }
  }, [me]);

  async function save() {
    setSaved(false);
    setSavedInputDeviceId(inputDeviceId);
    setSavedOutputDeviceId(outputDeviceId);
    await updateProfile.mutateAsync({
      captions_default: captionsDefault,
      speaking_rate: speakingRate,
      echo_cancellation: echoCancellation,
      noise_suppression: noiseSuppression,
    });
    setSaved(true);
  }

  return (
    <div className="flex flex-col gap-6">
      <div>
        <label className="block text-xs text-[var(--text-secondary)]" htmlFor="input-device">
          Microphone
        </label>
        <select
          id="input-device"
          value={inputDeviceId}
          onChange={(e) => setInputDeviceId(e.target.value)}
          className="mt-1 w-full rounded-md border bg-[var(--bg-card)] px-3 py-2 text-sm"
        >
          <option value="">System default</option>
          {inputDevices.map((d) => (
            <option key={d.deviceId} value={d.deviceId}>
              {d.label || `Microphone ${d.deviceId.slice(0, 6)}`}
            </option>
          ))}
        </select>

        <label className="mt-4 block text-xs text-[var(--text-secondary)]" htmlFor="output-device">
          Speaker
        </label>
        <select
          id="output-device"
          value={outputDeviceId}
          onChange={(e) => setOutputDeviceId(e.target.value)}
          className="mt-1 w-full rounded-md border bg-[var(--bg-card)] px-3 py-2 text-sm"
        >
          <option value="">System default</option>
          {outputDevices.map((d) => (
            <option key={d.deviceId} value={d.deviceId}>
              {d.label || `Speaker ${d.deviceId.slice(0, 6)}`}
            </option>
          ))}
        </select>
        {inputDevices.length === 0 && (
          <p className="mt-1 text-xs text-[var(--text-tertiary)]">
            Device names appear once you&apos;ve granted microphone access at least once.
          </p>
        )}
      </div>

      <label className="flex items-center justify-between text-sm">
        Echo cancellation
        <input
          type="checkbox"
          checked={echoCancellation}
          onChange={(e) => setEchoCancellation(e.target.checked)}
        />
      </label>
      <label className="flex items-center justify-between text-sm">
        Noise suppression
        <input
          type="checkbox"
          checked={noiseSuppression}
          onChange={(e) => setNoiseSuppression(e.target.checked)}
        />
      </label>
      <label className="flex items-center justify-between text-sm">
        Show captions by default
        <input
          type="checkbox"
          checked={captionsDefault}
          onChange={(e) => setCaptionsDefault(e.target.checked)}
        />
      </label>

      <div>
        <label className="flex items-center justify-between text-xs text-[var(--text-secondary)]" htmlFor="speaking-rate">
          <span>Persona speaking rate</span>
          <span className="font-mono">{speakingRate.toFixed(2)}×</span>
        </label>
        <input
          id="speaking-rate"
          type="range"
          min={0.5}
          max={2}
          step={0.05}
          value={speakingRate}
          onChange={(e) => setSpeakingRate(Number(e.target.value))}
          className="mt-2 w-full"
        />
      </div>

      <div className="flex items-center gap-3">
        <Button variant="primary" onClick={() => void save()} disabled={updateProfile.isPending}>
          {updateProfile.isPending ? "Saving…" : "Save"}
        </Button>
        {saved && <span className="text-xs text-[var(--text-tertiary)]">Saved.</span>}
      </div>

      <AudioCheckPanel constraints={{ deviceId: inputDeviceId || undefined, echoCancellation, noiseSuppression }} />
    </div>
  );
}
