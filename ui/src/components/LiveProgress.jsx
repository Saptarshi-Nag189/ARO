export default function LiveProgress({ agents, agentStates, iteration, message }) {
  const prettyName = (name) => name.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())

  return (
    <div className="progress-panel">
      <div className="pipeline">
        {agents.map((agent, i) => (
          <span key={agent}>
            {i > 0 && <span className="pipeline-arrow"> → </span>}
            <span className={`pipeline-node ${agentStates[agent] || ''}`}>
              {prettyName(agent)}
            </span>
          </span>
        ))}
      </div>
      <div className="progress-status">{message}</div>
      {iteration > 0 && (
        <div className="progress-iteration">Iteration {iteration}</div>
      )}
    </div>
  )
}
