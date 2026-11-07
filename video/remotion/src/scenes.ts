// Feedback cut: 'appr/' holds the half-size (960x540) copies of the appr_1080 clips, same frame counts; switch back to 'appr_1080/' for the 1080p final.
// Scene table of the Kaiku submission cut (body = everything after the 227-frame opener). Times in seconds.
export type Cap = {a: number; b: number; text: string; id: string};
export type Scene = {id: string; kind: 'desk' | 'phone' | 'trailer' | 'end'; src?: string; from?: number; dur: number; caps: Cap[]; tap?: number; rate?: number; sample?: boolean; still?: boolean};
export const FPS = 30;
export const SCENES: Scene[] = [
  {id: 'home', kind: 'desk', src: 'appr/A.mp4', from: 0, dur: 9, sample: true, caps: [{id: 'h1', a: 0.3, b: 4.3, text: 'Listing score 50: four things to fix.'}, {id: 'h2', a: 4.6, b: 8.8, text: 'Christmas Eve, a typo, a review, a period.'}]},
  {id: 'cards', kind: 'desk', src: 'appr/B.mp4', from: 0, dur: 8, sample: true, caps: [{id: 'k1', a: 0.3, b: 4.2, text: 'Accept, suggest a change, or discard.'}, {id: 'k2', a: 4.5, b: 7.9, text: 'Every suggestion carries its reason.'}]},
  {id: 'acc1', kind: 'desk', src: 'appr/C.mp4', from: 0, dur: 6.3, sample: true, rate: 1.6, caps: [{id: 'a1', a: 0.2, b: 6.1, text: 'Accept: Kaiku asks, one word fixes it.'}]},
  {id: 'acc2', kind: 'desk', src: 'appr/C.mp4', from: 11, dur: 5, sample: true, rate: 0.8, caps: [{id: 'a2', a: 1.3, b: 3.7, text: 'Saved to Yext, read back, shown on Fonecta.'}, {id: 'a3', a: 3.8, b: 4.9, text: 'Score 50 to 60.'}]},
  {id: 'acc3', kind: 'desk', src: 'appr/C.mp4', from: 16, dur: 4.8, sample: true, rate: 1.5, caps: [{id: 'a4', a: 0.2, b: 4.6, text: 'Changed last year too. Make it recurring? Yes.'}]},
  {id: 'more', kind: 'desk', src: 'appr/D.mp4', from: 0, dur: 9, sample: true, caps: [{id: 'm1', a: 0.3, b: 4.5, text: 'A typo and an unanswered review. Same loop.'}, {id: 'm2', a: 4.8, b: 8.8, text: 'Kaiku drafts the reply, the owner decides.'}]},
  {id: 'phonepage', kind: 'phone', src: 'appr/P.mp4', from: 0, dur: 6, sample: true, caps: [{id: 'p1', a: 0.3, b: 5.8, text: 'The same page on a phone. Nothing to install.'}]},
  {id: 'r_email', kind: 'phone', src: 'appr/phone_email.png', from: 0, dur: 3.2, still: true, caps: [{id: 'r0', a: 0.15, b: 3.1, text: 'No login: an email with a decision link.'}]},
  {id: 'r_wa', kind: 'phone', src: 'appr/phone_wa.png', from: 0, dur: 3.2, still: true, caps: [{id: 'r1', a: 0.15, b: 3.1, text: 'No reply: WhatsApp, answer in your own words.'}]},
  {id: 'r_call', kind: 'phone', src: 'appr/phone_call.png', from: 0, dur: 3.2, still: true, caps: [{id: 'r2', a: 0.15, b: 3.1, text: 'Still no reply: Kaiku calls.'}]},
  {id: 'reliab', kind: 'desk', src: 'appr/F.mp4', from: 4, dur: 9, sample: true, caps: [{id: 'f1', a: 0.2, b: 4.2, text: "Father's Day: no change, with the reason."}, {id: 'f2', a: 4.6, b: 8.8, text: 'Closed on Sundays, not a public holiday.'}]},
  {id: 'fiware', kind: 'desk', src: 'appr/G.mp4', from: 0, dur: 8, sample: true, caps: [{id: 'g1', a: 0.3, b: 3.9, text: 'Orion-LD is the spine of the chain.'}, {id: 'g2', a: 4.2, b: 7.9, text: 'Subscription fires for 24.12. in the live view.'}]},
  {id: 'aura', kind: 'desk', src: 'cap/aura.mp4', from: 6, dur: 8, caps: [{id: 'u1', a: 0.3, b: 7.7, text: 'Aura: live Turku buses and ships, same broker.'}]},
  {id: 'roomx', kind: 'desk', src: 'cap/room.mp4', from: 2, dur: 6, caps: [{id: 'q1', a: 0.3, b: 5.7, text: 'Scan the QR: own one Turku business.'}]},
  {id: 'trailer', kind: 'trailer', src: 'trailer.mp4', from: 0, dur: 20, caps: []},
  {id: 'end', kind: 'end', dur: 6.5, caps: []},
];
export const BODY_FRAMES = SCENES.reduce((s, x) => s + Math.round(x.dur * FPS), 0);
