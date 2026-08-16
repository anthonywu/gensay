import {AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig} from 'remotion';
import {theme} from '../theme';
import {SCENES, voiceCues} from '../voiceSchedule';

// Local vs cloud: the core positioning of gensay's provider lineup.
// `id` matches promo/generate_voices.py / voice-durations.json.
const LOCAL = [
  {id: 'chatterbox', name: 'Chatterbox', note: 'open model · warm daemon'},
  {id: 'vibevoice', name: 'VibeVoice', note: 'open model · MLX · new'},
  {id: 'macos', name: 'macOS say', note: 'native · zero setup'},
];

const CLOUD = [
  {id: 'elevenlabs', name: 'ElevenLabs', note: 'premium voices'},
  {id: 'deepgram', name: 'Deepgram', note: 'Flux · Aura'},
  {id: 'gemini', name: 'Gemini', note: 'prompt-steerable · new'},
  {id: 'openai', name: 'OpenAI', note: 'gpt-4o-mini-tts'},
  {id: 'polly', name: 'Amazon Polly', note: 'neural · long-form'},
];

// Provider currently speaking its roll-call line, given this scene's local
// frame. Cue frames are absolute, so shift by the grid scene start.
const speakingId = (localFrame: number): string | null => {
  const f = localFrame + SCENES.grid;
  const cue = voiceCues.find((c) => f >= c.from && f < c.from + c.durationInFrames + 4);
  return cue ? cue.id : null;
};

const Column: React.FC<{
  title: string;
  subtitle: string;
  accent: string;
  items: Array<{id: string; name: string; note: string}>;
  footer?: string;
  delay: number;
}> = ({title, subtitle, accent, items, footer, delay}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const speaking = speakingId(frame);

  const enter = spring({frame: frame - delay, fps, config: {damping: 200}});
  const slide = interpolate(enter, [0, 1], [50, 0]);

  return (
    <div
      style={{
        flex: 1,
        backgroundColor: theme.bgAccent,
        borderRadius: 26,
        border: `2px solid ${accent}44`,
        padding: '44px 50px',
        transform: `translateY(${slide}px)`,
        opacity: enter,
        display: 'flex',
        flexDirection: 'column',
      }}
    >
      <div
        style={{
          fontFamily: theme.mono,
          fontSize: 34,
          fontWeight: 700,
          color: accent,
          textTransform: 'uppercase',
          letterSpacing: 8,
        }}
      >
        {title}
      </div>
      <div
        style={{
          fontFamily: theme.sans,
          fontSize: 28,
          color: theme.subtext,
          marginTop: 8,
          marginBottom: 32,
        }}
      >
        {subtitle}
      </div>
      <div style={{display: 'flex', flexDirection: 'column', gap: 20, flex: 1}}>
        {items.map((p, i) => {
          const pop = spring({
            frame: frame - delay - 8 - i * 4,
            fps,
            config: {damping: 14, stiffness: 140},
          });
          const active = speaking === p.id;
          return (
            <div
              key={p.name}
              style={{
                display: 'flex',
                alignItems: 'baseline',
                justifyContent: 'space-between',
                backgroundColor: theme.bg,
                borderRadius: 14,
                padding: '20px 28px',
                transform: `scale(${active ? pop * 1.04 : pop})`,
                border: `2px solid ${active ? accent : 'transparent'}`,
                boxShadow: active ? `0 0 36px ${accent}66` : 'none',
              }}
            >
              <span
                style={{fontFamily: theme.sans, fontSize: 34, fontWeight: 700, color: theme.text}}
              >
                {p.name}
              </span>
              <span style={{fontFamily: theme.mono, fontSize: 22, color: accent}}>{p.note}</span>
            </div>
          );
        })}
      </div>
      {footer ? (
        <div
          style={{
            marginTop: 28,
            fontFamily: theme.mono,
            fontSize: 24,
            color: accent,
            textAlign: 'center',
          }}
        >
          {footer}
        </div>
      ) : null}
    </div>
  );
};

export const ProvidersGrid: React.FC = () => {
  const frame = useCurrentFrame();
  const {durationInFrames} = useVideoConfig();

  const fadeOut = interpolate(frame, [durationInFrames - 8, durationInFrames], [1, 0], {
    extrapolateLeft: 'clamp',
  });

  return (
    <AbsoluteFill
      style={{
        backgroundColor: theme.bg,
        opacity: fadeOut,
        padding: '60px 90px',
        justifyContent: 'center',
      }}
    >
      <div
        style={{
          fontFamily: theme.sans,
          fontSize: 60,
          fontWeight: 700,
          color: theme.text,
          textAlign: 'center',
          marginBottom: 44,
          opacity: interpolate(frame, [0, 12], [0, 1], {extrapolateRight: 'clamp'}),
        }}
      >
        Same command · <span style={{color: theme.accent4}}>state-of-the-art voices</span>
      </div>
      <div style={{display: 'flex', gap: 44, alignItems: 'stretch'}}>
        <Column
          title="Cloud"
          subtitle="fast · abundant voices · 70+ languages"
          accent={theme.accent4}
          items={CLOUD}
          footer="auto-fallback to macOS say when offline"
          delay={4}
        />
        <Column
          title="Or go local"
          subtitle="free · private · SOTA open models"
          accent={theme.accent2}
          items={LOCAL}
          footer="gensay daemon start → models stay warm"
          delay={40}
        />
      </div>
    </AbsoluteFill>
  );
};
