import {
  AbsoluteFill,
  OffthreadVideo,
  interpolate,
  spring,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from 'remotion';
import {theme} from '../theme';

// A caption header + an embedded VHS terminal recording. The clip is sped up
// so its full length fits exactly within the scene's duration.
export const TerminalScene: React.FC<{
  clip: string;
  clipSeconds: number;
  kicker: string;
  headline: string;
  accent: string;
}> = ({clip, clipSeconds, kicker, headline, accent}) => {
  const frame = useCurrentFrame();
  const {fps, durationInFrames} = useVideoConfig();
  const playbackRate = Math.max(1, (clipSeconds * fps) / durationInFrames);

  const enter = spring({frame, fps, config: {damping: 200}});
  const slide = interpolate(enter, [0, 1], [60, 0]);
  const fadeOut = interpolate(frame, [durationInFrames - 8, durationInFrames], [1, 0], {
    extrapolateLeft: 'clamp',
  });

  return (
    <AbsoluteFill style={{backgroundColor: theme.bg, opacity: fadeOut, padding: 70}}>
      <div style={{marginBottom: 34, transform: `translateY(${slide}px)`, opacity: enter}}>
        <div
          style={{
            fontFamily: theme.mono,
            fontSize: 30,
            color: accent,
            textTransform: 'uppercase',
            letterSpacing: 6,
            marginBottom: 12,
          }}
        >
          {kicker}
        </div>
        <div style={{fontFamily: theme.sans, fontSize: 58, fontWeight: 700, color: theme.text}}>
          {headline}
        </div>
      </div>
      <div
        style={{
          flex: 1,
          display: 'flex',
          justifyContent: 'center',
          alignItems: 'flex-start',
          transform: `translateY(${slide}px)`,
          opacity: enter,
        }}
      >
        <OffthreadVideo
          muted
          playbackRate={playbackRate}
          src={staticFile(clip)}
          style={{
            width: '88%',
            borderRadius: 18,
            boxShadow: `0 24px 90px rgba(0,0,0,0.6), 0 0 0 1px ${accent}33`,
          }}
        />
      </div>
    </AbsoluteFill>
  );
};
