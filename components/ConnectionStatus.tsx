"use client";

import { useSyncExternalStore } from "react";
import { ChevronLeft, WifiOff } from "lucide-react";

function subscribe(onStoreChange: () => void): () => void {
  window.addEventListener("online", onStoreChange);
  window.addEventListener("offline", onStoreChange);
  return () => {
    window.removeEventListener("online", onStoreChange);
    window.removeEventListener("offline", onStoreChange);
  };
}

function getSnapshot(): boolean {
  return navigator.onLine;
}

function getServerSnapshot(): boolean {
  return true;
}

export function ConnectionStatus() {
  const online = useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
  if (online) return null;

  return (
    <aside className="connection-banner" role="status" aria-live="polite">
      <span className="connection-icon"><WifiOff size={19} /></span>
      <span><strong>الاتصال مقطوع.</strong> القرار الظاهر ما عادش يتحدّث ببيانات جديدة وما يأكدش حالة البحر الحالية.</span>
      <a href="#field-checklist">قائمة السلامة <ChevronLeft size={15} /></a>
    </aside>
  );
}
