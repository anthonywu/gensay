import {AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig} from 'remotion';
import {theme} from '../theme';

export const Title: React.FC = () => {
  const frame = useCurrentFrame();
  const {fps, durationInFrames} = useVideoConfig();

  const pop = spring({frame, fps, config: {damping: 12, stiffness: 120}});
  const tagOpacity = interpolate(frame, [18, 34], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
  const fadeOut = interpolate(frame, [durationInFrames - 10, durationInFrames], [1, 0], {
    extrapolateLeft: 'clamp',
  });

  return (
    <AbsoluteFill
      style={{
        justifyContent: 'center',
        alignItems: 'center',
        opacity: fadeOut,
        background: `radial-gradient(circle at 50% 40%, ${theme.bgAccent} 0%, ${theme.bg} 70%)`,
      }}
    >
      <div
        style={{
          fontFamily: theme.mono,
          fontSize: 160,
          fontWeight: 700,
          color: theme.text,
          transform: `scale(${pop})`,
        }}
      >
        <span style={{color: theme.subtext}}>$ </span>
        <span style={{color: theme.accent}}>gen</span>say
      </div>
      <div
        style={{
          fontFamily: theme.sans,
          fontSize: 44,
          color: theme.subtext,
          marginTop: 30,
          opacity: tagOpacity,
        }}
      >
        One <code style={{color: theme.accent3}}>say</code>. Every voice.
      </div>
    </AbsoluteFill>
  );
};
