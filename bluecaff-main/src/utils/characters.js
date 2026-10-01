import calmIcon from "../assets/icons/calm.svg";
export const defaultCharacters = [
  {
    id: "serene",
    name: "Serene",
    tone: "Calm & Meditative",
    traits: ["Peaceful", "Thoughtful", "Wise"],
    description: "Speaks with tranquil composure, using metaphors about nature and mindfulness. Perfect for relaxed conversations.",
    icon: calmIcon,
    color: "#8B5CF6",
  },
  {
    id: "spark",
    name: "Spark",
    tone: "Energetic & Playful",
    traits: ["Enthusiastic", "Witty", "Fast-paced"],
    description: "High-energy and quick-witted responses with humor and excitement. Great for brainstorming sessions.",
    icon: calmIcon,
    color: "#10B981",
  },
  {
    id: "warmth",
    name: "Warmth",
    tone: "Caring & Supportive",
    traits: ["Empathetic", "Nurturing", "Gentle"],
    description: "Soft and reassuring voice that makes you feel heard and understood. Ideal for emotional support.",
    icon: calmIcon,
    color: "#EC4899",
  },
  {
    id: "sharp",
    name: "Sharp",
    tone: "Direct & Analytical",
    traits: ["Logical", "Precise", "No-nonsense"],
    description: "Straight to the point with clear, structured responses. Best for focused problem-solving.",
    icon: calmIcon,
    color: "#F59E0B",
  },
  {
    id: "confident",
    name: "Confident",
    tone: "Bold & Authoritative",
    traits: ["Assertive", "Strategic", "Professional"],
    description: "Executive presence with decisive, action-oriented guidance. Perfect for business discussions.",
    icon: calmIcon,
    color: "#3B82F6",
  },
];

// Helper to get characters from localStorage
export const getStoredCharacters = () => {
  const stored = localStorage.getItem('customCharacters');
  return stored ? JSON.parse(stored) : [];
};

// Helper to save custom character
export const saveCustomCharacter = (character) => {
  const existing = getStoredCharacters();
  localStorage.setItem('customCharacters', JSON.stringify([...existing, character]));
};

// Helper to delete custom character
export const deleteCustomCharacter = (id) => {
  const existing = getStoredCharacters();
  localStorage.setItem('customCharacters', JSON.stringify(existing.filter(c => c.id !== id)));
};

// Get all characters (default + custom)
export const getAllCharacters = () => {
  return [...defaultCharacters, ...getStoredCharacters()];
};
