import { useEffect, useState } from "react";
import { ASSET_ROOT } from "../data/assets";

export function VideoBackground({ angled = false }: { angled?: boolean }) {
  const [tilted, setTilted] = useState(false);

  useEffect(() => {
    if (!angled) {
      setTilted(false);
      return;
    }

    setTilted(false);
    let secondFrame = 0;
    const firstFrame = window.requestAnimationFrame(() => {
      secondFrame = window.requestAnimationFrame(() => setTilted(true));
    });

    return () => {
      window.cancelAnimationFrame(firstFrame);
      window.cancelAnimationFrame(secondFrame);
    };
  }, [angled]);

  return (
    <div className={angled ? `video-shell video-shell--angled${tilted ? " video-shell--tilted" : ""}` : "video-shell"}>
      <video autoPlay muted loop playsInline preload="auto">
        <source src={`${ASSET_ROOT}/raw/output.mp4`} type="video/mp4" />
        <source src={`${ASSET_ROOT}/raw/input.mp4`} type="video/mp4" />
      </video>
      <div className="video-vignette" />
    </div>
  );
}
