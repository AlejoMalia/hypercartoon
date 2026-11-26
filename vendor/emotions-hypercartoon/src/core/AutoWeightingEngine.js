/**
 * AutoWeightingEngine — Homeostatic Synaptic Plasticity & Neuromodulated Gain Control
 *
 * Grounded in:
 * - Turrigiano & Nelson (2004): Homeostatic plasticity keeps neural circuits within
 *   a stable functional dynamic range, preventing runaway excitation or silencing.
 * - Aston-Jones & Cohen (2005): Neuromodulatory gain control (cortisol, dopamine,
 *   arousal) dynamically recalibrates signal salience across cognitive networks.
 * - Sarter, Givens & Bruno (2001): Dynamic attentional effort and neurochemical gating.
 *
 * Provides automatic, adaptive weight regulation for all EmotionsHypercartoon subsystems:
 * 1. Derives baseline priors from Big Five personality traits (no arbitrary hardcoded weights).
 * 2. Neuromodulates gain in real-time based on cortisol, dopamine RPE, and allostatic load.
 * 3. Applies homeostatic synaptic scaling to avoid saturation/paralysis from hyperactive channels.
 * 4. Learns from relational feedback (rupture-repair and mutual reciprocity).
 */

function clamp( val, min = 0, max = 1 ) {

	return Math.max( min, Math.min( max, val ) )

}

export class AutoWeightingEngine {

	constructor( { personality = null } = {} ) {

		this.personality = personality
		this.channels = [
			'threat',
			'defense',
			'affiliation',
			'curiosity',
			'socialPain',
			'repair',
			'inhibition',
			'expression',
			'intuition',
			'pragmatics',
		]

		// Synaptic gains initialized to 1.0 (baseline)
		this.homeostaticGains = new Map()
		for ( const channel of this.channels ) {

			this.homeostaticGains.set( channel, 1.0 )

		}

		// Sliding window of recent activations to track chronic saturation
		this.activationHistory = new Map()
		for ( const channel of this.channels ) {

			this.activationHistory.set( channel, [] )

		}

		// Trait-derived baseline priors
		this.traitPriors = this.#computeTraitPriors()

	}

	#computeTraitPriors() {

		if ( !this.personality ) {

			const def = new Map()
			for ( const c of this.channels ) def.set( c, 1.0 )
			return def

		}

		const n = this.personality.get( 'neuroticism' ) ?? 0.5
		const o = this.personality.get( 'openness' ) ?? 0.5
		const e = this.personality.get( 'extraversion' ) ?? 0.5
		const a = this.personality.get( 'agreeableness' ) ?? 0.5
		const c = this.personality.get( 'conscientiousness' ) ?? 0.5

		return new Map( [
			[ 'threat', 0.6 + n * 0.8 ],
			[ 'defense', 0.5 + ( 1 - a ) * 0.5 + n * 0.4 ],
			[ 'affiliation', 0.5 + a * 0.6 + e * 0.4 ],
			[ 'curiosity', 0.4 + o * 0.8 + e * 0.2 ],
			[ 'socialPain', 0.5 + n * 0.7 + ( 1 - a ) * 0.3 ],
			[ 'repair', 0.5 + a * 0.7 + c * 0.3 ],
			[ 'inhibition', 0.5 + c * 0.8 + ( 1 - e ) * 0.2 ],
			[ 'expression', 0.4 + e * 0.7 + o * 0.3 ],
			[ 'intuition', 0.5 + o * 0.6 + n * 0.3 ],
			[ 'pragmatics', 0.5 + o * 0.5 + a * 0.4 + c * 0.3 ],
		] )

	}

	/**
	 * Computes the real-time neuromodulatory multiplier for each functional channel
	 * based on physiological signals (cortisol, dopamine, allostatic load, sleep debt).
	 */
	getNeuromodulators( { cortisol = 0, dopamineRpe = 0, allostaticLoad = 0, sleepDebt = 0 } = {} ) {

		const stress = clamp( cortisol * 0.7 + allostaticLoad * 0.3 )
		const reward = clamp( Math.max( 0, dopamineRpe ) )
		const exhaustion = clamp( sleepDebt / 24 )

		return {
			threat      : 1.0 + stress * 0.8 - exhaustion * 0.2,
			defense     : 1.0 + stress * 0.9,
			affiliation : 1.0 + reward * 0.5 - stress * 0.4,
			curiosity   : Math.max( 0.2, 1.0 + reward * 0.7 - stress * 0.6 - exhaustion * 0.4 ),
			socialPain  : 1.0 + stress * 0.6,
			repair      : 1.0 + ( 1 - stress ) * 0.4,
			inhibition  : Math.max( 0.2, 1.0 - exhaustion * 0.6 - stress * 0.3 ),
			expression  : Math.max( 0.3, 1.0 - stress * 0.5 - exhaustion * 0.3 ),
			intuition   : 1.0 + stress * 0.3,
			pragmatics  : Math.max( 0.3, 1.0 - exhaustion * 0.5 ),
		}

	}

	/**
	 * Returns the automatically computed effective weight for a given subsystem channel.
	 */
	computeEffectiveWeight( channel, baseWeight = 0.3, state = {} ) {

		const traitPrior = this.traitPriors.get( channel ) ?? 1.0
		const homeostaticGain = this.homeostaticGains.get( channel ) ?? 1.0
		const neuromodulators = this.getNeuromodulators( state )
		const neuroMultiplier = neuromodulators[ channel ] ?? 1.0

		const rawWeight = baseWeight * traitPrior * homeostaticGain * neuroMultiplier

		// Soft saturation curve (sigmoidal bounds between 0.05 and 1.5)
		return clamp( rawWeight, 0.05, 1.5 )

	}

	/**
	 * Records activation of a channel for homeostatic scaling and sliding window monitoring.
	 */
	recordActivation( channel, magnitude ) {

		const hist = this.activationHistory.get( channel )
		if ( !hist ) return

		hist.push( clamp( magnitude ) )
		if ( hist.length > 20 ) hist.shift()

		// Periodic synaptic scaling check
		this.#scaleHomeostatically( channel )

	}

	/**
	 * Turrigiano Homeostatic Synaptic Scaling:
	 * If average activity is persistently too high (>0.7), downscale synaptic gain.
	 * If average activity is quiescent (<0.1) over multiple turns, gradually restore sensitivity.
	 */
	#scaleHomeostatically( channel ) {

		const hist = this.activationHistory.get( channel )
		if ( !hist || hist.length < 5 ) return

		const avg = hist.reduce( ( a, b ) => a + b, 0 ) / hist.length
		let gain = this.homeostaticGains.get( channel ) ?? 1.0

		if ( avg > 0.75 ) {

			// Saturated channel: down-regulate gain
			gain = Math.max( 0.3, gain * 0.92 )

		}
		else if ( avg < 0.15 && gain < 1.4 ) {

			// Quiescent channel: up-regulate sensitivity
			gain = Math.min( 1.5, gain * 1.04 )

		}

		this.homeostaticGains.set( channel, gain )

	}

	/**
	 * Adapts synaptic weights in response to relational feedback (e.g. successful repair).
	 */
	adaptFromFeedback( { repaired = false, rupture = false, reciprocity = 0 } = {} ) {

		if ( repaired ) {

			// Reinforce repair and affiliation circuits
			const rGain = this.homeostaticGains.get( 'repair' ) ?? 1.0
			const aGain = this.homeostaticGains.get( 'affiliation' ) ?? 1.0
			this.homeostaticGains.set( 'repair', Math.min( 1.5, rGain * 1.05 ) )
			this.homeostaticGains.set( 'affiliation', Math.min( 1.5, aGain * 1.05 ) )

			// De-escalate chronic defense gain
			const dGain = this.homeostaticGains.get( 'defense' ) ?? 1.0
			this.homeostaticGains.set( 'defense', Math.max( 0.4, dGain * 0.9 ) )

		}
		else if ( rupture ) {

			// Increase alertness / defense gain
			const dGain = this.homeostaticGains.get( 'defense' ) ?? 1.0
			const tGain = this.homeostaticGains.get( 'threat' ) ?? 1.0
			this.homeostaticGains.set( 'defense', Math.min( 1.6, dGain * 1.1 ) )
			this.homeostaticGains.set( 'threat', Math.min( 1.6, tGain * 1.08 ) )

		}

		if ( reciprocity > 0.5 ) {

			const afGain = this.homeostaticGains.get( 'affiliation' ) ?? 1.0
			this.homeostaticGains.set( 'affiliation', Math.min( 1.5, afGain * 1.03 ) )

		}

	}

	toJSON() {

		return {
			homeostaticGains  : Object.fromEntries( this.homeostaticGains ),
			traitPriors       : Object.fromEntries( this.traitPriors ),
		}

	}

	fromJSON( data ) {

		if ( data?.homeostaticGains ) {

			this.homeostaticGains = new Map( Object.entries( data.homeostaticGains ) )

		}
		if ( data?.traitPriors ) {

			this.traitPriors = new Map( Object.entries( data.traitPriors ) )

		}

	}

}
