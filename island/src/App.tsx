import { useRef } from "react";
import "./App.css";
import { useDrag } from "./hooks/useDrag";

export default function App() {
  const hudRef = useRef<HTMLDivElement>(null);
  useDrag(hudRef);
  return (
    <div className="hud" ref={hudRef}>
      <div className="hud-placeholder">drag me</div>
    </div>
  );
}
