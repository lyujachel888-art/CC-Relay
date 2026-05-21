import { describe, it, expect, beforeEach } from "vitest";
import { useSessions } from "./sessions";

describe("sessions store", () => {
  beforeEach(() => { useSessions.setState({ map: new Map() }); });

  it("creates a session on first event for a project", () => {
    useSessions.getState().ingest({ type: "tool_use", project: "RC", text: "Bash: ls", meta: "" });
    const s = useSessions.getState().map.get("RC")!;
    expect(s.state).toBe("working");
    expect(s.color).toBe("p5");
    expect(s.history).toHaveLength(1);
  });

  it("appends history dots up to 5, then trims oldest", () => {
    const ing = useSessions.getState().ingest;
    for (let i = 0; i < 7; i++) ing({ type: "tool_use", project: "RC", text: "Bash: x", meta: "" });
    expect(useSessions.getState().map.get("RC")!.history).toHaveLength(5);
  });

  it("stores assistant_reply text as recap", () => {
    useSessions.getState().ingest({ type: "assistant_reply", project: "RC", text: "all done", meta: "" });
    expect(useSessions.getState().map.get("RC")!.recap).toBe("all done");
  });

  it("toggleRecap flips recapOpen", () => {
    useSessions.getState().ingest({ type: "assistant_reply", project: "RC", text: "x", meta: "" });
    useSessions.getState().toggleRecap("RC");
    expect(useSessions.getState().map.get("RC")!.recapOpen).toBe(true);
    useSessions.getState().toggleRecap("RC");
    expect(useSessions.getState().map.get("RC")!.recapOpen).toBe(false);
  });

  it("markIdle flips a stale session to idle", () => {
    useSessions.getState().ingest({ type: "tool_use", project: "RC", text: "Bash: x", meta: "" });
    useSessions.getState().markIdle("RC");
    expect(useSessions.getState().map.get("RC")!.state).toBe("idle");
    expect(useSessions.getState().map.get("RC")!.color).toBe("p8");
  });
});
