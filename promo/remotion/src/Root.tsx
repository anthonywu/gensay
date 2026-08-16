import {Composition} from 'remotion';
import {SizzleReel} from './SizzleReel';

export const RemotionRoot: React.FC = () => {
  return (
    <Composition
      id="Sizzle"
      component={SizzleReel}
      durationInFrames={900} // 30s @ 30fps
      fps={30}
      width={1920}
      height={1080}
    />
  );
};
