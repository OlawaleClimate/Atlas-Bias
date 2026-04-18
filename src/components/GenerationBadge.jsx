export default function GenerationBadge({ generation, severity }) {
  const cls = severity === "strong" ? "badge bad" : severity === "absent" ? "badge ok" : "badge warn";
  return (
    <span className={cls}>
      {generation}: {severity}
    </span>
  );
}
