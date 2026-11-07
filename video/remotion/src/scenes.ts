// v3 film scene table (no opener: the trailer opens the film). Times in seconds. Clip folders: HALF=true reads the half-size copies (public/v3h, public/caph; 540p feedback cut), false the 1080p ones (public/v3, public/cap).
export type Cap = {a: number; b: number; text: string; id: string};
export type Scene = {id: string; kind: 'desk' | 'phone' | 'trailer' | 'end'; src?: string; from?: number; dur: number; caps: Cap[]; tap?: number; rate?: number; sample?: boolean; still?: boolean; zoom?: {s: number; ox: number; oy: number}; slot?: string};
export const FPS = 30;
const HALF = true; // phone clips: playwright's 780x1688 video holds the 390x844 page in its top-left quarter; v3/phone.mp4 and v3/decide.mp4 are that quarter cropped (upscaled 2x in v3/, native in v3h/)
const V = HALF ? 'v3h/' : 'v3/';
const C = HALF ? 'caph/' : 'cap/';
export const SCENES: Scene[] = [
  // 1 trailer first (636 frames = 21.2 s, rendered by video/trailer, product video/products/kaiku_v3.json)
  {id: 'trailer', kind: 'trailer', src: V + 'trailer.mp4', from: 0, dur: 21.2, caps: []},
  // 2 homepage, new interface
  {id: 'home', kind: 'desk', src: V + 'home.mp4', from: 1.0, dur: 7, caps: [{id: 'h1', a: 0.3, b: 4.3, text: 'Listing score 40%: four things to fix.'}, {id: 'h2', a: 4.5, b: 6.9, text: 'Accept, suggest a change, or discard.'}]},
  // 3 chain + phone decision (first cut captures, same captions)
  {id: 'c1', kind: 'desk', src: C + 'desktop.mp4', from: 7.0, dur: 4, caps: [{id: 'c1', a: 0.2, b: 3.9, text: 'Broker subscription fires: hours missing.'}]},
  {id: 'c2', kind: 'desk', src: C + 'desktop.mp4', from: 11.5, dur: 4, caps: [{id: 'c2', a: 0.2, b: 3.9, text: 'The owner gets a link, no login.'}]},
  {id: 'p1', kind: 'phone', src: V + 'phone.mp4', from: 3.2, dur: 5, tap: 1.26, caps: [{id: 'p1', a: 0.2, b: 4.8, text: 'One tap: Hyväksy approves.'}]},
  {id: 'p2', kind: 'phone', src: V + 'phone.mp4', from: 9.6, dur: 3.5, caps: [{id: 'p2', a: 0.2, b: 3.4, text: 'It lists where the change shows.'}]},
  {id: 'c3', kind: 'desk', src: C + 'desktop.mp4', from: 18.0, dur: 4, caps: [{id: 'c3', a: 0.2, b: 3.9, text: 'Decision: approve, from the phone.'}]},
  {id: 'c4', kind: 'desk', src: C + 'desktop.mp4', from: 22.0, dur: 4, caps: [{id: 'c4', a: 0.2, b: 3.9, text: 'Hours saved to Yext, read back and verified.'}]},
  {id: 'c5', kind: 'desk', src: C + 'desktop.mp4', from: 26.0, dur: 3, caps: [{id: 'c5', a: 0.2, b: 2.9, text: 'Learned: the same suggestion next time.'}]},
  // 4 the new question on the decision page
  {id: 'chq', kind: 'phone', src: V + 'decide.mp4', from: 3.2, dur: 4.6, caps: [{id: 'q1', a: 0.2, b: 4.4, text: 'Email, WhatsApp or a call next time? It remembers.'}]},
  // 5 the chat on the new interface
  {id: 'ch1', kind: 'desk', src: V + 'chat.mp4', from: 6.4, dur: 4.6, caps: [{id: 'x1', a: 0.2, b: 1.9, text: 'Accept: Kaiku asks, one word fixes it.'}, {id: 'x2', a: 2.0, b: 4.5, text: 'Saved to Yext, read back, shown on Fonecta.'}]},
  {id: 'ch2', kind: 'desk', src: V + 'chat.mp4', from: 11.0, dur: 4.7, rate: 1.4, caps: [{id: 'x3', a: 0.2, b: 4.5, text: 'Changed last year too. Make it recurring? Yes.'}]},
  {id: 'ch3', kind: 'desk', src: V + 'chat.mp4', from: 17.6, dur: 4.6, caps: [{id: 'x4', a: 0.2, b: 4.4, text: 'Next time: WhatsApp. Kaiku remembers.'}]},
  // 6 voice: PLACEHOLDER (orb listening); the owner's voice-note exchange replaces this scene's source, see NOTES v3
  {id: 'voice', kind: 'desk', src: V + 'voice.mp4', from: 2.0, dur: 10, slot: 'voice', zoom: {s: 2.2, ox: 0.975, oy: 0.975}, caps: [{id: 'v1', a: 0.3, b: 9.5, text: "Don't want to type? Talk to it."}]},
  // 7 end card, held still
  {id: 'end', kind: 'end', dur: 6.5, caps: []},
];
export const BODY_FRAMES = SCENES.reduce((s, x) => s + Math.round(x.dur * FPS), 0);
