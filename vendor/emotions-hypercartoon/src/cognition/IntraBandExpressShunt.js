/**
 * IntraBandExpressShunt — Intra-Tier Cognitive Routing & Affective Shunting
 *
 * Implements variable impedance tunnels and express subcortical pathways
 * between psychological mechanisms of the same operational band (e.g., Affective Band:
 * Humor/Play vs Sadness/Grief vs Defensive Anger vs Tender Affinity):
 * - Modulates signal transmission velocity and impedance based on convergence state
 *   of Orders R3, R5, R7, and R11.
 * - Somatic Exhaustion or Cynical Boundary ($R_7, R_{11}$) shunts Sadness and Defensive
 *   Threat through zero-latency express tunnels, while applying high impedance to Humor.
 * - Autonomic Safety and Authenticity ($R_3, R_5$) shunts Humor and Tender Banter
 *   through instantaneous express pathways, while dampening paranoid defenses.
 *
 * Grounded in:
 * - LeDoux (1996): The Emotional Brain — Subcortical fast route (low road) vs cortical slow route (high road).
 * - Posner & Petersen (1990): The attention system of the human brain.
 * - Gross (2002): Emotion regulation: Affective, cognitive, and social consequences.
 */

function clamp01( v ) {

	return Math.max( 0, Math.min( 1, v ) )

}

export class IntraBandExpressShunt {

	constructor() {

		// Base latencies for affective channels (in milliseconds)
		this.baseLatencies = {
			humorPlay      : 350,
			griefSadness   : 400,
			defensiveAnger : 200,
			tenderAffinity : 300,
		}

	}

	/**
	 * Computes dynamic impedance, transmission priorities, and latency shifts
	 * across same-band affective channels.
	 *
	 * @param {Object} polygonalConvergence - Full report from PolygonalTriangulationCatalog
	 * @param {Object} personality - Big Five personality traits
	 * @returns {Object} { expressChannel, channelGains, latencies, activeTunnels }
	 */
	routeAffectiveBand( {
		polygonalConvergence = {},
		personality = {},
	} = {} ) {

		const r3 = polygonalConvergence.triangulation ?? {}
		const r5 = polygonalConvergence.pentangulation ?? {}
		const r7 = polygonalConvergence.heptangulation ?? {}
		const r11 = polygonalConvergence.endecangulation ?? {}

		const isMasked = r3.maskDetected ?? false
		const maskTension = r3.maskIndex ?? 0
		const somaticDensity = r7.psychologicalDensity ?? 0.5
		const isExhausted = somaticDensity > 0.6 || r7.somaticPresence === 'dense_saturation'
		const posture = r11.ethicalPosture ?? 'balanced_reciprocity'
		const isGuarded = posture === 'unyielding_boundary' || posture === 'cynical_detachment'
		const isResonant = r5.directive === 'resonant_complicity' || r5.directive === 'soothing_anchor'

		const E = personality.extraversion ?? 0.5
		const N = personality.neuroticism ?? 0.5
		const A = personality.agreeableness ?? 0.5

		// Initialize channel properties
		// impedance: 0 (superconductor / express route) to 1.0 (blocked / impenetrable)
		// gain: multiplier for channel activation
		// latencyShiftMs: negative for express speedup, positive for impedance delay
		const channels = {
			humorPlay : {
				impedance      : 0.3,
				gain           : 1.0,
				latencyShiftMs : 0,
				status         : 'standard',
			},
			griefSadness : {
				impedance      : 0.3,
				gain           : 1.0,
				latencyShiftMs : 0,
				status         : 'standard',
			},
			defensiveAnger : {
				impedance      : 0.4,
				gain           : 1.0,
				latencyShiftMs : 0,
				status         : 'standard',
			},
			tenderAffinity : {
				impedance      : 0.3,
				gain           : 1.0,
				latencyShiftMs : 0,
				status         : 'standard',
			},
		}

		// Condition A: Somatic Exhaustion or Cynical Boundary ($R_7, R_{11}, R_3$)
		// Triggers Threat / Grief Express Tunnel & High Impedance on Humor
		if ( isExhausted || isGuarded || ( isMasked && maskTension > 0.5 ) ) {

			// Sadness and defense enter express subcortical shunt
			channels.griefSadness.impedance = 0.05
			channels.griefSadness.gain = 1.8 + N * 0.6
			channels.griefSadness.latencyShiftMs = -180
			channels.griefSadness.status = 'express_tunnel'

			channels.defensiveAnger.impedance = 0.1
			channels.defensiveAnger.gain = 1.6 + ( 1 - A ) * 0.8
			channels.defensiveAnger.latencyShiftMs = -120
			channels.defensiveAnger.status = 'express_tunnel'

			// Humor is throttled / blocked by high emotional impedance
			channels.humorPlay.impedance = 0.85
			channels.humorPlay.gain = 0.2
			channels.humorPlay.latencyShiftMs = +350
			channels.humorPlay.status = 'high_impedance'

			channels.tenderAffinity.impedance = 0.7
			channels.tenderAffinity.gain = 0.4
			channels.tenderAffinity.latencyShiftMs = +200
			channels.tenderAffinity.status = 'throttled'

		}
		// Condition B: Safe Co-Regulation & Authentic Resonance ($R_5, R_3$)
		// Triggers Humor & Tenderness Express Shunt & High Impedance on Defensive Paranoia
		else if ( isResonant && !isMasked && somaticDensity < 0.45 ) {

			// Humor enters zero-latency playful banter express route
			channels.humorPlay.impedance = 0.05
			channels.humorPlay.gain = 1.7 + E * 0.6
			channels.humorPlay.latencyShiftMs = -150
			channels.humorPlay.status = 'express_tunnel'

			// Tender affinity enters fast-track connection
			channels.tenderAffinity.impedance = 0.08
			channels.tenderAffinity.gain = 1.6 + A * 0.7
			channels.tenderAffinity.latencyShiftMs = -120
			channels.tenderAffinity.status = 'express_tunnel'

			// Threat channels encounter heavy impedance
			channels.defensiveAnger.impedance = 0.8
			channels.defensiveAnger.gain = 0.25
			channels.defensiveAnger.latencyShiftMs = +250
			channels.defensiveAnger.status = 'high_impedance'

			channels.griefSadness.impedance = 0.65
			channels.griefSadness.gain = 0.4
			channels.griefSadness.latencyShiftMs = +150
			channels.griefSadness.status = 'throttled'

		}

		// Determine dominant express channel
		let dominantExpress = null
		let minImpedance = 1.0
		for ( const [ name, chan ] of Object.entries( channels ) ) {

			if ( chan.status === 'express_tunnel' && chan.impedance < minImpedance ) {

				minImpedance = chan.impedance
				dominantExpress = name

			}

		}

		this.lastRouting = {
			dominantExpressChannel : dominantExpress,
			channels,
			isExhaustionShuntActive : isExhausted || isGuarded,
			isPlayfulShuntActive    : isResonant && !isMasked,
			expressSummary          : dominantExpress
				? `Express tunnel active for [${dominantExpress}] (impedance: ${channels[ dominantExpress ].impedance.toFixed( 2 )}, latency: ${channels[ dominantExpress ].latencyShiftMs}ms)`
				: 'Equally distributed intra-band transmission',
		}

		return this.lastRouting

	}

	/**
	 * Returns the current impedance map across affective channels.
	 */
	getImpedanceSnapshot() {

		if ( this.lastRouting ) return this.lastRouting.channels

		return {
			humorPlay      : { impedance: 0.5, gain: 1.0, latencyShiftMs: 0, status: 'baseline' },
			griefSadness   : { impedance: 0.5, gain: 1.0, latencyShiftMs: 0, status: 'baseline' },
			defensiveAnger : { impedance: 0.5, gain: 1.0, latencyShiftMs: 0, status: 'baseline' },
			tenderAffinity : { impedance: 0.5, gain: 1.0, latencyShiftMs: 0, status: 'baseline' },
		}

	}

}
