"use client";

import { useState, useSyncExternalStore } from "react";

import { clearDeviceKey, readDeviceKey, saveDeviceKey } from "@/lib/api";

const DEVICE_KEY_EVENT = "peche-tn:device-key-changed";

function hasDeviceKey(): boolean {
  return readDeviceKey() !== "";
}

function subscribeDeviceKey(onChange: () => void): () => void {
  window.addEventListener("storage", onChange);
  window.addEventListener(DEVICE_KEY_EVENT, onChange);
  return () => {
    window.removeEventListener("storage", onChange);
    window.removeEventListener(DEVICE_KEY_EVENT, onChange);
  };
}

function notifyDeviceKey(): void {
  window.dispatchEvent(new Event(DEVICE_KEY_EVENT));
}

export function DeviceKeyPanel() {
  const saved = useSyncExternalStore(
    subscribeDeviceKey,
    hasDeviceKey,
    () => false,
  );
  const [draft, setDraft] = useState("");
  const [message, setMessage] = useState("");

  const save = () => {
    const value = draft.trim();
    if (value.length < 8) {
      setMessage("المفتاح قصير جداً.");
      return;
    }
    saveDeviceKey(value);
    notifyDeviceKey();
    setDraft("");
    setMessage("حُفظ على هذا المتصفح. التحليل سيجلب البيانات من هاتفك.");
  };

  const remove = () => {
    clearDeviceKey();
    notifyDeviceKey();
    setMessage(
      "حُذف المفتاح من هذا المتصفح. التحليل سيجلب البيانات من الخادم.",
    );
  };

  return (
    <details className="device-key-panel" data-testid="device-key-panel">
      <summary>
        <strong>جلب البيانات من هاتفي</strong>{" "}
        <small>{saved ? "مفعّل" : "غير مفعّل"}</small>
      </summary>
      <p>
        للمالك فقط. يحفظ المفتاح في هذا المتصفح، ويرسل الهاتف بيانات Open-Meteo
        مع الطلب. بدون المفتاح يجلب الخادم البيانات كالمعتاد.
      </p>
      <p>
        <strong>تنبيه:</strong> localStorage ليس خزنة أسرار. لا تشارك المفتاح،
        ولا تستعمل هذا الجهاز لغيرك.
      </p>
      <label>
        <span>مفتاح الجهاز</span>
        <input
          type="password"
          autoComplete="off"
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          placeholder={saved ? "••••••••" : "أدخل المفتاح"}
        />
      </label>
      <div className="device-key-actions">
        <button type="button" onClick={save} disabled={draft.trim() === ""}>
          حفظ المفتاح
        </button>
        {saved && (
          <button type="button" onClick={remove}>
            حذف من هذا المتصفح
          </button>
        )}
      </div>
      {message && <p role="status">{message}</p>}
    </details>
  );
}
