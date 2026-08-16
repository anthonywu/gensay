import {AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig} from 'remotion';
import {theme} from '../theme';

const FEATURES = [
  'streaming playback',
  'audio caching',
  'offline fallback',
  'REPL mode',
  'shell completions',
  'multi-speaker dialogue',
  'warm daemon',
];

export const Closing: React.FC = () => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();

  const pop = spring({frame, fps, config: {damping: 14, stiffness: 130}});
  const tickerOpacity = interpolate(frame, [14, 28], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });

  return (
    <AbsoluteFill
      style={{
        justifyContent: 'center',
        alignItems: 'center',
        background: `radial-gradient(circle at 50% 45%, ${theme.bgAccent} 0%, ${theme.bg} 70%)`,
      }}
    >
      <div
        style={{
          fontFamily: theme.mono,
          fontSize: 66,
          color: theme.text,
          backgroundColor: theme.bgAccent,
          border: `2px solid ${theme.accent}55`,
          borderRadius: 18,
          padding: '34px 60px',
          transform: `scale(${pop})`,
        }}
      >
        <span style={{color: theme.subtext}}>$ </span>
        uv tool install <span style={{color: theme.accent2}}>gensay</span>
      </div>
      <div
        style={{
          marginTop: 50,
          fontFamily: theme.sans,
          fontSize: 30,
          color: theme.subtext,
          opacity: tickerOpacity,
          maxWidth: 1400,
          textAlign: 'center',
          lineHeight: 1.6,
        }}
      >
        {FEATURES.join('  ·  ')}
      </div>
      <div
        style={{
          marginTop: 40,
          fontFamily: theme.mono,
          fontSize: 32,
          color: theme.accent,
          opacity: tickerOpacity,
        }}
      >
        github.com/anthonywu/gensay
      </div>
    </AbsoluteFill>
  );
};
