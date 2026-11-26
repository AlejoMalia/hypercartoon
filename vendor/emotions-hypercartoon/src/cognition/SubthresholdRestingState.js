/**
 * SubthresholdRestingState — Spontaneous Background Noise & Default Mode Network (DMN)
 *
 * Implements spontaneous, subthreshold resting-state fluctuations for mechanisms
 * that are currently inactive or unprimed by explicit user input:
 * - Solves the mathematical dead-zero problem (no living circuit is at 0.000 Hz).
 * - Models 1/f pink noise, synaptic background hum, and resting-state wandering.
 * - Refracted through Big Five personality traits:
 *   - High Neuroticism: spontaneous threat/insecurity hum, faint suspicion.
 *   - High Openness: spontaneous associative drift, daydreaming and creative curiosity.
 *   - High Extraversion: spontaneous social pull, wanting connection.
 *   - High Conscientiousness: spontaneous order-seeking, task vigilance.
 * - Accounts for elapsed silence/time to drift resting thoughts.
 *
 * Grounded in:
 * - Raichle et al. (2001): A default mode of brain function (DMN).
 * - Faisal, Selen & Wolpert (2008): Noise in the nervous system.
 * - Deco, Jirsa & McIntosh (2011): Emerging concepts for the dynamical organization of resting-state activity.
 */

function clamp01( v ) {

	return Math.max( 0, Math.min( 1, v ) )

}

export class SubthresholdRestingState {

	constructor( { seed = 42 } = {} ) {

		this.step = 0
		this.lastWanderingThought = null
		this.seed = seed

	}

	/**
	 * Pseudo-random bounded pink-noise generator [0..1] with temporal smoothing.
	 */
	_stochasticPinkNoise( offset = 0 ) {

		this.step++
		// Sinusoidal multi-frequency superposition for organic 1/f-like wave fluctuation
		const t = ( this.step + offset + this.seed ) * 0.17
		const raw = Math.sin( t ) * 0.4 + Math.sin( t * 2.31 ) * 0.35 + Math.sin( t * 5.17 ) * 0.25

		// Map to [0..1]
		return clamp01( ( raw + 1 ) / 2 )

	}

	/**
	 * Evaluates resting-state fluctuations for currently inactive or dormant modules.
	 *
	 * @param {Object} personality - Big Five personality traits { neuroticism, openness, extraversion, conscientiousness, agreeableness }
	 * @param {Object} activeStates - Map of currently active values e.g. { jealousy: 0, grief: 0, humor: 0, suspicion: 0 }
	 * @param {number} elapsedMs - Silence/idle time in ms
	 * @returns {Object} { backgroundHum, activeFluctuations, wanderingThought }
	 */
	computeRestingHum( {
		personality = {},
		activeStates = {},
		elapsedMs = 0,
	} = {} ) {

		const N = personality.neuroticism ?? 0.5
		const O = personality.openness ?? 0.5
		const E = personality.extraversion ?? 0.5
		const C = personality.conscientiousness ?? 0.5
		const A = personality.agreeableness ?? 0.5

		const elapsedHours = elapsedMs / 3600000
		const idleDrift = Math.min( 0.5, elapsedHours * 0.05 )

		// 1. Threat / Insecurity Background Hum (Neuroticism-driven)
		// Active when jealousy, suspicion, or fear are low/dormant
		const rawThreatNoise = this._stochasticPinkNoise( 1 )
		const threatHum = clamp01(
			( activeStates.suspicion ?? 0 ) < 0.2
				? ( rawThreatNoise * 0.08 * ( 0.4 + N * 1.2 ) ) + ( N > 0.6 ? idleDrift * 0.1 : 0 )
				: 0
		)

		// 2. Associative Daydream Drift (Openness-driven)
		// Active when cognitive dissonance or rigid tasks are low
		const rawOpennessNoise = this._stochasticPinkNoise( 2 )
		const associativeDrift = clamp01(
			rawOpennessNoise * 0.07 * ( 0.3 + O * 1.4 ) + ( idleDrift * 0.08 )
		)

		// 3. Spontaneous Relational Pull / Loneliness Hum (Extraversion & Attachment)
		const rawSocialNoise = this._stochasticPinkNoise( 3 )
		const relationalPull = clamp01(
			( activeStates.bonding ?? 0 ) < 0.3
				? rawSocialNoise * 0.06 * ( 0.3 + E * 1.1 + ( 1 - A ) * 0.3 ) + ( E > 0.6 ? idleDrift * 0.15 : 0 )
				: 0
		)

		// 4. Somatic Micro-Tremor (Bodily conductance baseline)
		const rawSomaticNoise = this._stochasticPinkNoise( 4 )
		const somaticTremor = clamp01(
			rawSomaticNoise * 0.05 * ( 0.5 + N * 0.9 - C * 0.3 )
		)

		// Aggregate Subthreshold Hum Energy
		const totalHumEnergy = ( threatHum + associativeDrift + relationalPull + somaticTremor ) / 4

		// Synthesize qualitative subconscious wandering thought if idle time or openness is notable
		let wanderingTheme = null
		if ( threatHum > 0.06 ) {

			wanderingTheme = 'A faint residual anxiety flickers under the surface without a clear trigger.'

		}
		else if ( associativeDrift > 0.06 ) {

			wanderingTheme = 'Mind wanders across tangential memories and speculative what-ifs.'

		}
		else if ( relationalPull > 0.05 ) {

			wanderingTheme = 'An unspoken awareness of the other person lingers in the silence.'

		}
		else {

			wanderingTheme = 'Subconscious baseline is calm and homeostatically balanced.'

		}

		this.lastWanderingThought = wanderingTheme

		return {
			totalHumEnergy,
			fluctuations : {
				threatHum,
				associativeDrift,
				relationalPull,
				somaticTremor,
			},
			wanderingTheme,
			idleDrift,
		}

	}

}
