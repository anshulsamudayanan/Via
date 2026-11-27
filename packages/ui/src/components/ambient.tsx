/**
 * The light behind the glass: two static, near-neutral fields, like a bench lamp over a dark desk,
 * plus film grain. One fixed layer for the whole page; radial gradients rather than filter blur, so
 * it costs almost nothing to composite. Nothing drifts and nothing moves on scroll.
 */
export function Ambient() {
  return (
    <div aria-hidden="true" className="pointer-events-none fixed inset-0 -z-50 overflow-hidden bg-background">
      <div
        className="absolute -left-[15%] -top-[25%] size-[80vmax] rounded-full"
        style={{ background: "radial-gradient(closest-side, var(--via-ambient-1), transparent)" }}
      />
      <div
        className="absolute -bottom-[30%] -right-[20%] size-[70vmax] rounded-full"
        style={{ background: "radial-gradient(closest-side, var(--via-ambient-2), transparent)" }}
      />
      <div className="via-grain absolute inset-0" />
    </div>
  );
}
