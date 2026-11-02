/**
 * Simple hash function for strings
 */
function getHash(str) {
    let hash = 0;
    for (let i = 0; i < str.length; i++) {
        hash = str.charCodeAt(i) + ((hash << 5) - hash);
        hash = hash | 0; // Convert to 32bit integer
    }
    return Math.abs(hash);
}

// Curated list of pastel, 3-stop gradients based on user feedback
// Style: High lightness, medium saturation, smooth transitions
// `text` is a darker, saturated twin of each gradient (same hue order, Tailwind
// 700-900 tones, >= 4.5:1 on white). The light theme uses it for the node type
// label, handles and card border, where the pastel gradient is unreadable.
const PREDEFINED_PALETTES = [
    // 0. Blue -> Aqua -> Spring Green (User Ref: Agent)
    { gradient: 'linear-gradient(135deg, #a0c4ff, #99eaf9, #baf9b1)', shadow: 'rgba(153, 234, 249, 0.5)',
      text: 'linear-gradient(135deg, #1d4ed8, #155e75, #166534)' },

    // 1. Mint -> Teal -> Sky (User Ref: Model)
    { gradient: 'linear-gradient(135deg, #c7f9cc, #8ef6e4, #7bdff2)', shadow: 'rgba(123, 223, 242, 0.5)',
      text: 'linear-gradient(135deg, #166534, #115e59, #0369a1)' },

    // 2. Coral -> Apricot -> Butter (User Ref: Human)
    { gradient: 'linear-gradient(135deg, #ff9b9b, #ffb876, #ffe59d)', shadow: 'rgba(255, 184, 118, 0.5)',
      text: 'linear-gradient(135deg, #b91c1c, #9a3412, #92400e)' },

    // 3. Lemon -> Meadow -> Sky (User Ref: Subgraph)
    { gradient: 'linear-gradient(135deg, #fdf2a0, #baf9b1, #99eaf9)', shadow: 'rgba(186, 249, 177, 0.5)',
      text: 'linear-gradient(135deg, #854d0e, #166534, #155e75)' },

    // 4. Periwinkle -> Lavender -> Rose (User Ref: Python)
    { gradient: 'linear-gradient(135deg, #b4c5ff, #c9a7eb, #ffb4ed)', shadow: 'rgba(201, 167, 235, 0.5)',
      text: 'linear-gradient(135deg, #4338ca, #7e22ce, #be185d)' },

    // 5. Blossom -> Rose -> Peach
    { gradient: 'linear-gradient(135deg, #ffc6ff, #ff9ec7, #ffd6a5)', shadow: 'rgba(255, 158, 199, 0.5)',
      text: 'linear-gradient(135deg, #a21caf, #be185d, #9a3412)' },

    // 6. Lavender -> Denim -> Sky
    { gradient: 'linear-gradient(135deg, #e0c3fc, #a6c1ee, #8ec5fc)', shadow: 'rgba(166, 193, 238, 0.5)',
      text: 'linear-gradient(135deg, #7e22ce, #1d4ed8, #0369a1)' },

    // 7. Mint -> Sky -> Jade
    { gradient: 'linear-gradient(135deg, #d3f9d8, #a9def9, #9ee6a6)', shadow: 'rgba(169, 222, 249, 0.5)',
      text: 'linear-gradient(135deg, #166534, #0369a1, #065f46)' },

    // 8. Lemon -> Pear -> Seafoam
    { gradient: 'linear-gradient(135deg, #fef3a5, #c8f7c5, #8be0ce)', shadow: 'rgba(200, 247, 197, 0.5)',
      text: 'linear-gradient(135deg, #854d0e, #3f6212, #115e59)' },

    // 9. Peach -> Raspberry -> Honey
    { gradient: 'linear-gradient(135deg, #ffd8be, #ff9aa2, #ffc87c)', shadow: 'rgba(255, 154, 162, 0.5)',
      text: 'linear-gradient(135deg, #9a3412, #be123c, #92400e)' },

    // 10. Mist -> Lilac -> Blush
    { gradient: 'linear-gradient(135deg, #e8e9f3, #cddafd, #f6d6ff)', shadow: 'rgba(205, 218, 253, 0.5)',
      text: 'linear-gradient(135deg, #475569, #4338ca, #a21caf)' },

    // 11. Aqua -> Indigo -> Orchid
    { gradient: 'linear-gradient(135deg, #9efcff, #a9b8ff, #e3b4ff)', shadow: 'rgba(169, 184, 255, 0.5)',
      text: 'linear-gradient(135deg, #155e75, #4338ca, #7e22ce)' },

    // 12. Gold -> Orange -> Rose
    { gradient: 'linear-gradient(135deg, #fde68a, #fdba74, #fda4af)', shadow: 'rgba(253, 186, 116, 0.5)',
      text: 'linear-gradient(135deg, #92400e, #9a3412, #be123c)' },

    // 13. Emerald -> Teal -> Cerulean
    { gradient: 'linear-gradient(135deg,rgb(134, 247, 207),rgb(87, 224, 219),rgb(119, 175, 224))', shadow: 'rgba(76, 212, 208, 0.5)',
      text: 'linear-gradient(135deg, #065f46, #115e59, #075985)' },

    // 14. Warm Gray -> Sand -> Lilac
    { gradient: 'linear-gradient(135deg, #e6e0d4, #f7e7ce, #d4c5f5)', shadow: 'rgba(214, 197, 245, 0.5)',
      text: 'linear-gradient(135deg, #57534e, #713f12, #6d28d9)' }
];

// Cache for consistent mapping within a session to avoid collisions
const assignedColors = new Map();
const usedIndices = new Set();
// One frozen style object per palette: every node of a type shares the same
// reference, so Vue's :style patching has nothing to diff on re-render.
const styleByIndex = new Map();

function getPaletteStyle(index) {
    let style = styleByIndex.get(index);
    if (!style) {
        const palette = PREDEFINED_PALETTES[index];
        style = Object.freeze({
            '--node-gradient': palette.gradient,
            '--node-text-gradient': palette.text,
            '--node-shadow-color': palette.shadow
        });
        styleByIndex.set(index, style);
    }
    return style;
}

/**
 * Generate stable dynamic styles for a node based on its type string.
 * This ensures new node types automatically get distinct, pleasant colors
 * by mapping them to a curated list of harmonious palettes.
 * 
 * @param {string} nodeType - The type of the node (e.g., 'agent', 'python', 'custom')
 * @returns {Object} CSS variable overrides for the node
 */
export function getNodeStyles(nodeType) {
    if (!nodeType) return {};

    // Return cached assignment if exists
    if (assignedColors.has(nodeType)) {
        return getPaletteStyle(assignedColors.get(nodeType));
    }

    const hash = getHash(nodeType);
    const len = PREDEFINED_PALETTES.length;
    let index = hash % len + 1;

    // Open addressing: Linear probing to find the next available color slot
    // This helps avoid visual collisions for different node types in the same session
    for (let i = 0; i < len; i++) {
        const candidateIndex = (index + i) % len;
        if (!usedIndices.has(candidateIndex)) {
            index = candidateIndex;
            break;
        }
    }

    assignedColors.set(nodeType, index);
    usedIndices.add(index);

    return getPaletteStyle(index);
}
