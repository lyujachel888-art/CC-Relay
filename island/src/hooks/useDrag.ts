import { getCurrentWindow } from "@tauri-apps/api/window";
import { PhysicalPosition } from "@tauri-apps/api/dpi";
import { LazyStore } from "@tauri-apps/plugin-store";
import { useEffect } from "react";

const store = new LazyStore("island-state.json");
const KEY = "window_pos";

interface Pos { x: number; y: number; }

export function useDrag(ref: React.RefObject<HTMLElement | null>) {
  // restore on mount
  useEffect(() => {
    (async () => {
      const pos = await store.get<Pos>(KEY);
      if (pos) {
        await getCurrentWindow().setPosition(new PhysicalPosition(pos.x, pos.y));
      }
    })();
  }, []);

  // drag listener
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const onDown = async (e: MouseEvent) => {
      if (e.button !== 0) return;
      await getCurrentWindow().startDragging();
    };
    el.addEventListener("mousedown", onDown);
    return () => el.removeEventListener("mousedown", onDown);
  }, [ref]);

  // save on move-end (poll every 500ms, save if changed)
  useEffect(() => {
    let last: Pos | null = null;
    const id = setInterval(async () => {
      const pp = await getCurrentWindow().outerPosition();
      const cur = { x: pp.x, y: pp.y };
      if (!last || last.x !== cur.x || last.y !== cur.y) {
        await store.set(KEY, cur);
        await store.save();
        last = cur;
      }
    }, 500);
    return () => clearInterval(id);
  }, []);
}
