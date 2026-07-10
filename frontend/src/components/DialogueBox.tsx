import type { CSSProperties, ReactNode } from "react";

export function DialogueBox({
  title,
  children,
  timerKey,
  seconds = 10
}: {
  title: string;
  children: ReactNode;
  timerKey: string;
  seconds?: number;
}) {
  return (
    <section className="dialogue-box">
      <div className="dialogue-box__timer" key={timerKey} style={{ "--seconds": `${seconds}s` } as CSSProperties} />
      <h2>{title}</h2>
      <div>{children}</div>
    </section>
  );
}
