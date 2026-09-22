import { useEffect, useRef } from 'react';
import { voiceStore } from '../voiceStore';

export function Orb({ reduced, active }: {reduced: boolean; active: boolean}) {
  const ref = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const canvas = ref.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    let frame = 0, angle = 0, last = 0, pulse = 0;
    const points = Array.from({ length: 780 }, (_, i) => {
      const y = 1 - (i / 779) * 2;
      const radius = Math.sqrt(1 - y * y);
      const theta = Math.PI * (3 - Math.sqrt(5)) * i;
      return { x: Math.cos(theta) * radius, y, z: Math.sin(theta) * radius };
    });
    function draw(time: number) {
      if (!canvas || !ctx) return;
      if (time - last < 33 && !reduced) { frame = requestAnimationFrame(draw); return; }
      last = time;
      const width = canvas.clientWidth, height = canvas.clientHeight;
      const size = Math.min(width, height);
      const scale = Math.min(window.devicePixelRatio || 1, 2);
      if (canvas.width !== width * scale || canvas.height !== height * scale) { canvas.width = width * scale; canvas.height = height * scale; }
      ctx.setTransform(scale, 0, 0, scale, 0, 0);
      ctx.clearRect(0, 0, width, height);
      // Voice: the core swells with the sound actually being spoken or heard (eased, and still under reduced motion).
      const voice = voiceStore.get(), heard = voice.state === 'speaking' ? voice.levelOut : voice.state === 'listening' ? voice.levelIn * .6 : 0;
      pulse += (heard - pulse) * .25;
      const radius = size * .39 * (1 + pulse * .07), centerX = width / 2, centerY = height / 2;
      const glow = ctx.createRadialGradient(centerX, centerY, 0, centerX, centerY, radius * 1.3);
      glow.addColorStop(0, 'rgba(72,205,197,.04)'); glow.addColorStop(1, 'rgba(72,205,197,0)');
      ctx.fillStyle = glow; ctx.fillRect(0, 0, width, height);
      const projected = points.map(p => {
        const x = p.x * Math.cos(angle) - p.z * Math.sin(angle);
        const z = p.x * Math.sin(angle) + p.z * Math.cos(angle);
        return { x: centerX + x * radius, y: centerY + (p.y * .97 + z * .15) * radius, z };
      }).sort((a,b) => a.z - b.z);
      projected.forEach((p, i) => {
        const opacity = .12 + (p.z + 1) * .32;
        ctx.fillStyle = `rgba(${active || voice.state === 'speaking' || voice.state === 'listening' ? '125,244,231' : '124,210,208'},${opacity})`;
        ctx.beginPath(); ctx.arc(p.x, p.y, .45 + (p.z + 1) * .5, 0, Math.PI * 2); ctx.fill();
        if (i % 7 === 0 && p.z > .2) {
          const q = projected[i + 2];
          if (q && Math.hypot(q.x-p.x,q.y-p.y) < 25) {
            ctx.strokeStyle = 'rgba(96,202,198,.12)'; ctx.beginPath();ctx.moveTo(p.x,p.y);ctx.lineTo(q.x,q.y);ctx.stroke();
          }
        }
      });
      if (!reduced && !document.hidden) angle += active || voice.state === 'speaking' ? .008 : .002;
      if (!reduced) frame = requestAnimationFrame(draw);
    }
    frame = requestAnimationFrame(draw);
    const resize = new ResizeObserver(() => { if (reduced) draw(100); });
    resize.observe(canvas);
    return () => { cancelAnimationFrame(frame); resize.disconnect(); };
  }, [reduced, active]);
  return <canvas ref={ref} className="core-orb" aria-hidden="true" />;
}
