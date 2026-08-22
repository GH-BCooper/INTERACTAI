import { create } from "zustand";

export interface Toast {
  id: string;
  title: string;
  description?: string;
  action?: { label: string; onClick: () => void };
}

interface ToastState {
  toasts: Toast[];
  push: (toast: Omit<Toast, "id">) => string;
  dismiss: (id: string) => void;
}

/** Task 3.1: "Toast region, bottom right, used almost exclusively for 'your report is ready'."
 * A plain Zustand store rather than a context provider — toasts can be pushed from anywhere
 * (a TanStack Query mutation, a WS event handler) without needing to be inside a specific
 * component subtree. */
export const useToastStore = create<ToastState>((set) => ({
  toasts: [],
  push: (toast) => {
    const id = crypto.randomUUID();
    set((s) => ({ toasts: [...s.toasts, { ...toast, id }] }));
    return id;
  },
  dismiss: (id) => set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) })),
}));
