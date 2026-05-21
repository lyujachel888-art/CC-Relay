import type { Priority } from "../lib/colors";
import CatIdle from "./cats/Idle";
import CatWorking from "./cats/Working";
import CatDone from "./cats/Done";
import CatError from "./cats/Error";

export type CatState = "working" | "done" | "error" | "idle";

interface Props { state: CatState; priority: Priority; }

export default function FocusCat({ state, priority }: Props) {
  switch (state) {
    case "working": return <CatWorking priority={priority} />;
    case "done":    return <CatDone priority={priority} />;
    case "error":   return <CatError />;
    case "idle":    return <CatIdle />;
  }
}
