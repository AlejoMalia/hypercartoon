// Allow-list of the pure (deterministic, offline) script-hypercartoon engines that Hypercartoon uses.
// Nothing that calls a model, a network or a payment service is imported here. Only the basic screenplay-reading path
// (scene/camera/dialogue parsing, pacing tension, simple open-thread detection) is exported; the generic, cross-domain
// node-graph analysis of arbitrary prose is not exposed here.
export * as screenplay from './src/lib/nodes/screenplay.ts'
export * as completion from './src/lib/nodes/completion.ts'
export * as lexicon from './src/lib/nodes/lexicon.ts'
export * as rhythm from './src/lib/lenses/cinema/screenplay-rhythm.ts'
export * as scriptParser from './src/lib/storyboard/script-parser.ts'
export * as sceneSplitter from './src/lib/storyboard/scene-splitter.ts'
export * as emotionArc from './src/lib/utils/emotion-arc.ts'
export * as textMetrics from './src/lib/utils/text-metrics.ts'
