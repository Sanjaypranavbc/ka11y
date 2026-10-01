import { Phone, PhoneOff } from "lucide-react";
import "./CallButton.css";

const CallButton = ({ isActive, onToggle }) => {
  return (
    <button
      onClick={onToggle}
      className={`call-btn d-flex align-items-center justify-content-center rounded-circle 
        ${isActive ? "btn-danger active-call" : "btn-primary inactive-call"}`}
    >
      {!isActive && <span className="pulse-ring"></span>}

      {isActive ? (
        <PhoneOff size={22} className="text-white" />
      ) : (
        <Phone size={22} className="text-white" />
      )}
    </button>
  );
};

export default CallButton;
