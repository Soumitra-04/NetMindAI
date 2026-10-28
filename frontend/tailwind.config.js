/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        background: {
          DEFAULT: '#0B0F19',
          card: '#111827',
          panel: '#151D30',
          hover: '#1E293B',
          subtle: '#0F1626'
        },
        border: {
          subtle: '#1E293B',
          muted: '#28354D',
          highlight: '#38BDF8'
        },
        cyan: {
          accent: '#06B6D4',
          glow: 'rgba(6, 182, 212, 0.25)',
          bright: '#22D3EE'
        },
        violet: {
          accent: '#8B5CF6',
          muted: '#6D28D9',
          glow: 'rgba(139, 92, 246, 0.25)'
        },
        status: {
          healthy: '#10B981',
          warning: '#F59E0B',
          danger: '#EF4444',
          info: '#3B82F6'
        }
      },
      fontFamily: {
        mono: ['ui-monospace', 'SFMono-Regular', 'Menlo', 'Monaco', 'Consolas', 'monospace'],
        sans: ['Inter', 'system-ui', '-apple-system', 'BlinkMacSystemFont', 'Segoe UI', 'Roboto', 'sans-serif']
      }
    },
  },
  plugins: [],
}

