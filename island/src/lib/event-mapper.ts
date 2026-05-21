import type { Priority } from "./colors";
import type { CatState } from "../components/FocusCat";

export interface RawEvent {
  type: "tool_use" | "assistant_reply" | "user_prompt" | "bash_result" | "notification" | "task_created" | "task_completed";
  project: string;
  text: string;
  meta: string;
}

export interface MappedState { state: CatState; color: Priority; }

export function mapEvent(e: RawEvent): MappedState {
  switch (e.type) {
    case "tool_use": {
      if (/^Bash:/i.test(e.text))                                          return { state: "working", color: "p5" };
      if (/^(Read|Write|Edit|MultiEdit|NotebookEdit):/i.test(e.text))      return { state: "working", color: "p6" };
      if (/^(Glob|Grep|WebSearch|WebFetch):/i.test(e.text))                return { state: "working", color: "p7" };
      return { state: "working", color: "p5" };  // unknown tool — default active
    }
    case "user_prompt":     return { state: "working", color: "p7" };
    case "assistant_reply": return { state: "done",    color: "p4" };
    case "task_created":    return { state: "working", color: "p3" };
    case "task_completed":  return { state: "done",    color: "p3" };
    case "bash_result":     return e.meta === "fail"
                              ? { state: "error",   color: "p1" }
                              : { state: "working", color: "p5" };
    case "notification":    return { state: "error",   color: "p2" };
  }
}
