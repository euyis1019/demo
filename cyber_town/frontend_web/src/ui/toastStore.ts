import { create } from "zustand";

// 轻量 toast：升温里程碑 / 心意送达等即时反馈（焐心小镇支柱1/4）。
export interface Toast {
  id: number;
  text: string;
  kind: "milestone" | "info";
}

interface ToastState {
  list: Toast[];
  push: (text: string, kind?: Toast["kind"]) => void;
  dismiss: (id: number) => void;
}

let seq = 0;
export const useToast = create<ToastState>((set) => ({
  list: [],
  push: (text, kind = "info") => {
    const id = ++seq;
    set((s) => ({ list: [...s.list, { id, text, kind }] }));
    setTimeout(
      () => set((s) => ({ list: s.list.filter((t) => t.id !== id) })),
      kind === "milestone" ? 6000 : 3500,
    );
  },
  dismiss: (id) => set((s) => ({ list: s.list.filter((t) => t.id !== id) })),
}));
