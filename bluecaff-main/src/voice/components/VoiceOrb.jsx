import "./VoiceOrb.css";

const VoiceOrb = ({ isActive, isSpeaking, className = "" }) => {
  return (
    <div className={`voice-orb position-relative d-flex align-items-center justify-content-center ${className}`}>
      
      {/* Outer pulse rings */}
      {isActive && (
        <>
          <div className="pulse-ring ring-1"></div>
          <div className="pulse-ring ring-2"></div>
          <div className="pulse-ring ring-3"></div>
        </>
      )}

      {/* Glow */}
      <div
        className={`orb-glow ${isActive ? "glow-active" : "glow-inactive"}`}
      ></div>

      {/* Main orb */}
      <div
        className={`orb-main
          ${isActive ? "orb-active" : "orb-idle"}
          ${isSpeaking ? "orb-speaking" : ""}
        `}
      >
        {/* Inner shine */}
        <div className="orb-shine"></div>

        {/* Highlight */}
        <div className="orb-highlight"></div>

        {/* Speaking waves */}
        {isSpeaking && (
          <div className="wave-container d-flex align-items-center justify-content-center">
            <div className="d-flex gap-1">
              {[...Array(5)].map((_, i) => (
                <span
                  key={i}
                  className="wave-bar"
                  style={{
                    animationDelay: `${i * 100}ms`,
                    height: `${15 + Math.random() * 20}px`,
                  }}
                />
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Status ring */}
      <div
        className={`status-ring ${isActive ? "status-active" : "status-idle"}`}
      ></div>
    </div>
  );
};

export default VoiceOrb;
