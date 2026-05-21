import { describe, it, expect } from "vitest";
import { mapEvent } from "./event-mapper";

describe("mapEvent", () => {
  it("maps tool_use Bash:* → working/p5", () => {
    expect(mapEvent({ type: "tool_use", project: "RC", text: "Bash: ls", meta: "" }))
      .toEqual({ state: "working", color: "p5" });
  });

  it("maps tool_use Read/Write/Edit → working/p6", () => {
    expect(mapEvent({ type: "tool_use", project: "RC", text: "Read: foo.py", meta: "" }))
      .toEqual({ state: "working", color: "p6" });
    expect(mapEvent({ type: "tool_use", project: "RC", text: "Write: bar.ts", meta: "" }))
      .toEqual({ state: "working", color: "p6" });
  });

  it("maps tool_use Glob/Grep/WebSearch/WebFetch → working/p7", () => {
    expect(mapEvent({ type: "tool_use", project: "RC", text: "Glob: **/*.py", meta: "" }))
      .toEqual({ state: "working", color: "p7" });
    expect(mapEvent({ type: "tool_use", project: "RC", text: "WebFetch: example.com", meta: "" }))
      .toEqual({ state: "working", color: "p7" });
  });

  it("maps assistant_reply → done/p4", () => {
    expect(mapEvent({ type: "assistant_reply", project: "RC", text: "ok", meta: "" }))
      .toEqual({ state: "done", color: "p4" });
  });

  it("maps task_completed → done/p3", () => {
    expect(mapEvent({ type: "task_completed", project: "RC", text: "", meta: "" }))
      .toEqual({ state: "done", color: "p3" });
  });

  it("maps user_prompt → working/p7", () => {
    expect(mapEvent({ type: "user_prompt", project: "RC", text: "hi", meta: "" }))
      .toEqual({ state: "working", color: "p7" });
  });

  it("maps bash_result fail → error/p1", () => {
    expect(mapEvent({ type: "bash_result", project: "RC", text: "$ ls", meta: "fail" }))
      .toEqual({ state: "error", color: "p1" });
  });

  it("maps bash_result ok → working/p5", () => {
    expect(mapEvent({ type: "bash_result", project: "RC", text: "$ ls", meta: "ok" }))
      .toEqual({ state: "working", color: "p5" });
  });

  it("maps notification → error/p2", () => {
    expect(mapEvent({ type: "notification", project: "RC", text: "Hey", meta: "" }))
      .toEqual({ state: "error", color: "p2" });
  });
});
