import "./StatusBadge.css";
import { useLanguage } from "../../Components/LanguageSelector";
import { getTranslation } from "../../utils/translations";

const statusConfig = {
  idle: {
    label: "Ready to connect",
    color: "bg-secondary",
    pulse: false,
  },
  connecting: {
    label: "Connecting...",
    color: "bg-warning",
    pulse: true,
  },
  active: {
    label: "Listening",
    color: "bg-success",
    pulse: true,
  },
  speaking: {
    label: "Speaking",
    color: "bg-primary",
    pulse: true,
  },
};

const StatusBadge = ({ status }) => {
  const { language } = useLanguage();
  const config = statusConfig[status];

  return (
    <div className="status-badge d-flex align-items-center gap-2 px-3 py-2 rounded-pill">
      <div className="position-relative">
        <span className={`status-dot ${config.color}`}></span>

        {config.pulse && (
          <span className={`status-pulse ${config.color}`}></span>
        )}
      </div>

      <span className="status-label">{getTranslation(language, `voice.${status}`)}</span>
    </div>
  );
};

export default StatusBadge;
