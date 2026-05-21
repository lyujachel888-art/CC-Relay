export type Priority = "p1" | "p2" | "p3" | "p4" | "p5" | "p6" | "p7" | "p8";

/** Maps a Priority to the hex value of its main color (used for trail dots). */
export const COLOR_MAIN: Record<Priority, string> = {
  p1: "#EF4444",  // CRITICAL · error
  p2: "#F97316",  // HIGH · notification
  p3: "#EAB308",  // CELEBRATE · task complete
  p4: "#10B981",  // DONE · assistant reply
  p5: "#6366F1",  // ACTIVE · Bash
  p6: "#8B5CF6",  // WORKING · file ops
  p7: "#06B6D4",  // INPUT · user prompt
  p8: "#6B7280",  // IDLE · no activity
};
