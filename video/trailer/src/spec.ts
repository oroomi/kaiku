import React from 'react';
import proofroom from '../products/proofroom.json';

export type IconName = 'page' | 'play' | 'wave' | 'receipt' | 'anchor';

export type LineSpec = {
  /** the words of the line, separated by single spaces (one word = one pop) */
  text: string;
  /** total width in px at the starting word gap: sets the type size, so a longer text gets smaller type */
  fit: number;
  /** vertical centre of the line in the 1080 px frame */
  cy: number;
  /** colour of the light across the line: [position 0..1, colour]. This is the per-word hue hint. */
  stops: [number, string][];
  /** text-shadow colours [tight, mid, wide] (optional) */
  glow?: string[];
  /** colours of the two end blooms [left, right] */
  blobs?: [string, string];
};

export type CardSpec = {
  title: string;
  /** a string, or an array of parts that are rendered as separate text nodes (only needed to match the first film pixel for pixel) */
  sub: string | string[];
  date: string | string[];
  status: string;
  /** path under public/ */
  thumb: string;
  /** object-position of the thumbnail (default 50% 50%) */
  pos?: string;
  zoom?: number;
  /** hue-rotate in degrees; only when set the colourising filter is applied (our own film stills use it, screenshots do not) */
  hue?: number;
};

export type PanelSpec = {img: string; col: number; row: number; cw: number; ch: number; label: string; appear: number; flip?: number};

export type Palette = {
  bg: string;
  /** stage radial gradient: centre, mid, edge */
  stage: [string, string, string];
  /** pill gradient stops */
  pill: [string, string, string, string];
  /** tile gradients (3 particles) */
  tiles: [string, string, string];
  /** optional override of the ten stage blooms: [colour, hot core] by index */
  blooms?: [string, string][];
};

export type Spec = {
  id: string;
  name: string;
  palette: 'krock' | Partial<Palette>;
  lines: {l1: LineSpec; l2: LineSpec; l3: LineSpec};
  pills: {icon: IconName; label: string}[];
  /** pill label font size in px (default 54); lower it for longer labels */
  pillLabelSize?: number;
  particles: {icons: IconName[]};
  screen: {
    name: string;
    breadcrumb: string;
    searchPlaceholder: string;
    actionButton: string;
    /** text of the small chip at the bottom of the empty-state box ("+" in the original) */
    uploadChip: string;
    /** optional label inside the empty-state box */
    emptyLabel?: string;
    /** the particle that flies in: the third icon tile, or a text chip */
    flyer: {chip?: string; chips?: string[]};
    loadingLabel: string;
    flipLabel: string;
    flips: {card: number; t: number}[];
    cards: CardSpec[];
    /** v3 extension: real pictures in the same 3D screen frame instead of the card grid (grid cell units) */
    panels?: PanelSpec[];
  };
  /** v3: extend = seconds added after the screen so a longer tagline can hold */
  timing?: {extend?: number};
  tagline: LineSpec;
  logo: {
    text: string;
    fit: number;
    stops: [number, string][];
    glow: string[];
    blob: string;
    /** small type line under the logo (optional) */
    url?: string;
  };
};

export const KROCK_PALETTE: Palette = {
  bg: '#0b0630',
  stage: ['#1e1056', '#150a44', '#08031e'],
  pill: ['#c447b6', '#a74fcb', '#6f78e6', '#2f93e4'],
  tiles: ['linear-gradient(135deg,#f35fc0,#b53bd0)', 'linear-gradient(135deg,#a863ee,#6f42d8)', 'linear-gradient(135deg,#59b4ff,#2f78e6)'],
};

export const resolvePalette = (p: Spec['palette']): Palette => (p === 'krock' ? KROCK_PALETTE : {...KROCK_PALETTE, ...p});

export const DEFAULT_SPEC = proofroom as unknown as Spec;
export const SpecContext = React.createContext<Spec>(DEFAULT_SPEC);
export const useSpec = () => React.useContext(SpecContext);
export const usePalette = () => resolvePalette(useSpec().palette);
export const words = (s: string) => s.split(' ');

/** render options: sprites = use the pre-rendered PNG blooms/rim (public/sprites); set live=true in the props to force the original CSS layers */
export const OptsContext = React.createContext<{sprites: boolean}>({sprites: true});
export const useSprites = () => {
  const o = React.useContext(OptsContext);
  const spec = useSpec();
  const p = spec.palette;
  const custom = p !== 'krock' && !!(p.bg || p.stage || p.blooms);
  return o.sprites && !custom;
};
