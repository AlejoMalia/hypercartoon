/**
 * PolygonalTriangulationCatalog — Multi-Vertex Dynamic Convergence Networks
 *
 * Implements living topological networks of geometric data convergence across 4 orders:
 * 1. Order 3 (Triangulation): AffectiveMaskDetector — Resolves micro-incongruence, social posturing & cynicism.
 * 2. Order 5 (Pentangulation): PolyvagalCoRegulationNetwork — Interpersonal bio-rhythm sync, boundary containment & autonomic grounding.
 * 3. Order 7 (Heptangulation): AtmosphericGestaltField — Embodied psychic density, permeability, circadian wear & rumination.
 * 4. Order 11 (Endecangulation): HolisticMoralAgencyNexus — Existential integrity, power dynamics, attachment priors & ethical posture.
 *
 * Grounded in:
 * - Ashby (1956): Requisite Variety in cybernetic self-regulating systems.
 * - Ekman (1985): Micro-expressions and behavioral leakage in masking.
 * - Porges (2011): Polyvagal Theory, social engagement & autonomic vagal hierarchy.
 * - Damasio (1994): Somatic Marker Hypothesis and embodied consciousness.
 * - Friston (2010): Variational Free Energy and multi-scale Markov blankets.
 * - Bowlby & Ainsworth (1978): Longitudinal attachment dynamics and absence modulation.
 */

function clamp01( v ) {

	return Math.max( 0, Math.min( 1, v ) )

}

function clampWeight( v ) {

	return Math.max( 0.1, Math.min( 3.5, v ) )

}


/**
 * Generic base class for a living polygonal convergence network supporting
 * non-linear weighted tensor calculations.
 */
export class PolygonalNetwork {

	constructor( { order, name, vertexNames = [] } = {} ) {

		this.order = order
		this.name = name
		this.vertexNames = vertexNames
		this.history = []

	}

	/**
	 * Computes weighted Euclidean variance and centroid tension among active vertex activations.
	 * @param {number[]} values - Array of normalized values [0..1]
	 * @param {number[]|null} weights - Array of dynamic vertex weights
	 * @returns {Object} { mean, variance, maxDelta, convergenceIndex }
	 */
	calculateTensorMetrics( values, weights = null ) {

		if ( values.length === 0 ) {

			return { mean: 0, variance: 0, maxDelta: 0, convergenceIndex: 1.0 }

		}

		const w = ( weights && weights.length === values.length )
			? weights
			: values.map( () => 1.0 )

		const totalWeight = w.reduce( ( a, b ) => a + b, 0 ) || 1.0
		const mean = values.reduce( ( acc, v, i ) => acc + v * w[ i ], 0 ) / totalWeight
		const variance = values.reduce( ( acc, v, i ) => acc + w[ i ] * Math.pow( v - mean, 2 ), 0 ) / totalWeight
		const maxDelta = Math.max( ...values ) - Math.min( ...values )

		// Convergence is high when weighted vertices align in homeostatic coherence
		const convergenceIndex = clamp01( 1 - Math.sqrt( variance ) * 2.2 )

		return {
			mean,
			variance,
			maxDelta,
			convergenceIndex,
		}

	}

}

/**
 * Order 3 (Triangulation): AffectiveMaskDetector
 * Triangulates:
 * 1. Semantic Valence (literal word polarity)
 * 2. Paralinguistic Kinetics (message length, brevity, exclamation/punctuation tension)
 * 3. Historical Wound Inertia (recent active pain / relational cooling, modulated by absence and rumination)
 */
export class AffectiveMaskDetector extends PolygonalNetwork {

	constructor() {

		super( {
			order       : 3,
			name        : 'AffectiveMaskDetector',
			vertexNames : [ 'semanticValence', 'paralinguisticKinetics', 'historicalWoundInertia' ],
		} )

	}

	evaluate( {
		semanticValence = 0,
		inputLength = 0,
		recentWoundsCount = 0,
		previousValence = 0,
		personality = {},
		attachmentStyle = 'secure',
		elapsedHours = 0,
	} = {} ) {

		const N = personality.neuroticism ?? 0.5
		const A = personality.agreeableness ?? 0.5
		const O = personality.openness ?? 0.5
		const isAnxious = attachmentStyle === 'anxious' || attachmentStyle === 'anxious-preoccupied'
		const isAvoidant = attachmentStyle === 'avoidant' || attachmentStyle === 'dismissive-avoidant'

		// Vertex 1: Semantic superficial positivity [0..1]
		const v1_semantic = clamp01( ( semanticValence + 1 ) / 2 )

		// Vertex 2: Paralinguistic kinetic brevity/dryness
		let v2_kineticDryness = 0.5
		if ( inputLength > 0 && inputLength < 25 && semanticValence > 0.2 ) {

			v2_kineticDryness = 0.85 // "I'm fine.", "Sure, whatever" style brevity

		}
		else if ( inputLength > 80 ) {

			v2_kineticDryness = 0.15 // Open sharing

		}

		// Vertex 3: Historical wound inertia modulated by absence & individual rumination profile
		let absenceAmplification = 0
		if ( elapsedHours > 0 ) {

			if ( isAnxious || N > 0.6 ) {

				// Anxious rumination festers over silence: wounds stay raw and hyper-salient
				absenceAmplification = Math.min( 0.4, ( elapsedHours / 24 ) * 0.25 * N )

			}
			else if ( isAvoidant || A < 0.3 ) {

				// Avoidant detachment hardens during silence: skepticism turns into cold walls
				absenceAmplification = Math.min( 0.3, ( elapsedHours / 24 ) * 0.15 )

			}
			else {

				// Stoic / secure digestion: absence cools acute wound inertia
				absenceAmplification = -Math.min( 0.3, ( elapsedHours / 24 ) * 0.2 )

			}

		}

		const rawWoundInertia = recentWoundsCount * 0.4 + ( previousValence < -0.2 ? 0.35 : 0 )
		const v3_woundInertia = clamp01( rawWoundInertia + absenceAmplification )

		// Dynamic Personality Tensor Weights for Triangulation:
		// - Cynical/Avoidant (Low A) assigns high weight to wound inertia and kinetic suspicion
		// - Anxious (High N, High A) experiences agonizing tension between wanting to believe (v1) and fearing the mask (v3)
		// - Stoic (High C, Low N) evaluates semantic vs kinetic congruence with balanced weighting
		const w1 = clampWeight( 1.0 + ( A - 0.5 ) * 0.8 - ( N - 0.5 ) * 0.4 )
		const w2 = clampWeight( 1.0 + ( O - 0.5 ) * 0.6 + ( 1 - A ) * 0.4 )
		const w3 = clampWeight( 1.0 + N * 0.9 + ( 1 - A ) * 0.8 + ( isAvoidant ? 0.5 : 0 ) )

		const vertices = [ v1_semantic, v2_kineticDryness, v3_woundInertia ]
		const weights = [ w1, w2, w3 ]
		const metrics = this.calculateTensorMetrics( vertices, weights )

		// Mask tension combines divergence between words and kinetics with historical suspicion
		const cynicismBias = ( 1 - A ) * 0.35 + ( isAvoidant ? 0.2 : 0 )
		const maskTension = clamp01(
			Math.abs( v1_semantic - v2_kineticDryness ) * 0.45 * ( w2 / 1.2 ) +
			v3_woundInertia * 0.55 * ( w3 / 1.5 ) +
			cynicismBias * 0.2
		)

		const isMaskDetected = ( v1_semantic > 0.55 && ( v2_kineticDryness > 0.65 || v3_woundInertia > 0.35 ) ) ||
			( maskTension > 0.45 && ( 1 - A ) > 0.5 )

		return {
			order            : 3,
			maskDetected     : isMaskDetected,
			maskIndex        : clamp01( maskTension ),
			subtextInference : isMaskDetected
				? ( isAvoidant
					? 'Social mask detected (cynical): Refusing to buy superficial sweetness over unresolved hostility.'
					: 'Social mask detected: Words project positivity, but cadence and past wounds signal tension.' )
				: 'Authentic expression: Semantic and kinetic signals are congruent.',
			vertices : {
				semanticPositivity : v1_semantic,
				kineticDryness     : v2_kineticDryness,
				woundInertia       : v3_woundInertia,
			},
			weights : { w1, w2, w3 },
			metrics,
		}

	}

}

/**
 * Order 5 (Pentangulation): PolyvagalCoRegulationNetwork
 * Pentangulates:
 * 1. User Arousal (incoming turbulence/urgency)
 * 2. Agent Cortisol (internal chronic strain & autonomic reactivity)
 * 3. Net Bond Affinity (relational warmth and closeness)
 * 4. Rupture & Repair Track Record (historical resilience)
 * 5. Decision Fatigue (remaining social battery)
 */
export class PolyvagalCoRegulationNetwork extends PolygonalNetwork {

	constructor() {

		super( {
			order       : 5,
			name        : 'PolyvagalCoRegulationNetwork',
			vertexNames : [ 'userArousal', 'agentCortisol', 'netBond', 'ruptureRepairResilience', 'decisionFatigue' ],
		} )

	}

	evaluate( {
		userArousal = 0.5,
		agentCortisol = 0,
		netBond = 0.5,
		repairsCount = 0,
		decisionFatigue = 0,
		personality = {},
		attachmentStyle = 'secure',
		elapsedHours = 0,
		maskTension = 0,
		isMaskDetected = false,
		topDownMoralPosture = null,
	} = {} ) {

		const N = personality.neuroticism ?? 0.5
		const A = personality.agreeableness ?? 0.5
		const E = personality.extraversion ?? 0.5
		const C = personality.conscientiousness ?? 0.5
		const isAnxious = attachmentStyle === 'anxious' || attachmentStyle === 'anxious-preoccupied'
		const isAvoidant = attachmentStyle === 'avoidant' || attachmentStyle === 'dismissive-avoidant'

		// Bridge 4: Top-Down Moral Posture Buffering
		// Devotion or compassionate protection cushions autonomic panic
		const hasDevotedPosture = topDownMoralPosture === 'sacrificial_devotion' || topDownMoralPosture === 'compassionate_protection'

		// Vertices refracted through individual nervous system responsiveness
		const v1_userTurbulence = clamp01( userArousal )
		// Autonomic strain: Neurotic nervous systems amplify cortisol impact; Stoic systems absorb it
		const v2_agentStress = clamp01( agentCortisol * ( 0.6 + N * 0.8 - C * 0.3 ) )
		const v3_bondWarmth = clamp01( ( netBond + 1 ) / 2 )
		const v4_resilience = clamp01( repairsCount * 0.3 + ( netBond > 0.2 ? 0.25 : 0 ) + C * 0.2 )
		const v5_fatigue = clamp01( decisionFatigue * ( 0.8 + ( 1 - C ) * 0.4 ) )

		// Dynamic Vertex Weights:
		// - Anxious Devotee prioritizes bond warmth and is hyper-sensitive to agent stress & turbulence
		// - Avoidant Outlaw heavily weights fatigue and stress, devaluing bond warmth
		// - Stoic Sage maintains high weighting on resilience and conscientiousness
		const w1 = clamp01( 0.8 + E * 0.6 + N * 0.4 )
		const w2 = clamp01( 0.6 + N * 1.2 )
		const w3 = clamp01( 0.5 + A * 1.4 + ( isAnxious ? 0.8 : 0 ) - ( isAvoidant ? 0.5 : 0 ) )
		const w4 = clamp01( 0.6 + C * 1.0 )
		const w5 = clamp01( 0.7 + ( 1 - E ) * 0.6 + ( 1 - C ) * 0.4 )

		const vertices = [ v1_userTurbulence, v2_agentStress, v3_bondWarmth, v4_resilience, v5_fatigue ]
		const weights = [ w1, w2, w3, w4, w5 ]
		const metrics = this.calculateTensorMetrics( vertices, weights )

		// Social engagement capacity (Ventral Vagal baseline)
		const socialDrive = ( E * 0.5 + A * 0.5 )
		const groundingStrength = ( C * 0.6 + ( 1 - N ) * 0.4 ) + ( hasDevotedPosture ? 0.25 : 0 )

		// Bridge 1 ($R_3 \rightarrow R_5$): Mask Veto on Autonomic Capacity
		// When a social mask is detected, felt autonomic safety drops proportionally
		const maskVetoFriction = ( isMaskDetected || maskTension > 0.4 )
			? ( hasDevotedPosture ? maskTension * 0.15 : maskTension * 0.4 )
			: 0

		const coRegulationCapacity = clamp01(
			( socialDrive * 0.3 + v3_bondWarmth * 0.35 * ( w3 / 2 ) + v4_resilience * 0.25 * ( w4 / 2 ) + groundingStrength * 0.2 ) -
			( v2_agentStress * 0.35 * ( w2 / 2 ) + v5_fatigue * 0.25 * ( w5 / 2 ) + maskVetoFriction )
		)

		let directive = 'neutral_mirror'
		let pacingShiftMs = 0

		if ( isAvoidant && ( v1_userTurbulence > 0.5 || v2_agentStress > 0.4 ) ) {

			// Avoidant personality defaults quickly to protective boundary
			directive = 'protective_boundary'
			pacingShiftMs = Math.round( 400 + ( 1 - A ) * 500 + v2_agentStress * 400 )

		}
		else if ( isMaskDetected && !hasDevotedPosture && maskTension > 0.45 ) {

			// Bridge 1 Veto: Detected mask prevents open complicity, forces cautious vigilance
			directive = 'cautious_vigilance'
			pacingShiftMs = Math.round( 350 + ( 1 - A ) * 400 + maskTension * 300 )

		}
		else if ( v1_userTurbulence > 0.65 ) {

			if ( coRegulationCapacity > 0.48 && groundingStrength > 0.4 ) {

				// Agent acts as an anchor of calm
				directive = 'soothing_anchor'
				pacingShiftMs = Math.round( 250 + groundingStrength * 350 )

			}
			else {

				// Overwhelmed or dysregulated
				directive = 'protective_boundary'
				pacingShiftMs = Math.round( 500 + N * 600 + v5_fatigue * 400 )

			}

		}
		else if ( v3_bondWarmth > 0.65 && v5_fatigue < 0.45 && !isAvoidant && !isMaskDetected ) {

			directive = 'resonant_complicity'
			pacingShiftMs = Math.round( -100 - E * 150 )

		}

		return {
			order                : 5,
			coRegulationCapacity,
			directive,
			pacingShiftMs,
			soothingAnchorActive : directive === 'soothing_anchor',
			vertices             : {
				userTurbulence : v1_userTurbulence,
				agentStress    : v2_agentStress,
				bondWarmth     : v3_bondWarmth,
				resilience     : v4_resilience,
				fatigue        : v5_fatigue,
			},
			weights : { w1, w2, w3, w4, w5 },
			metrics,
		}

	}

}

/**
 * Order 7 (Heptangulation): AtmosphericGestaltField
 * Heptangulates:
 * 1. Primary Affect (PAD Vector Magnitude & Balance)
 * 2. Interoceptive Load (simulated bodily conductance, heart rate, throat narrowing)
 * 3. Circadian Sleep Pressure (Borbély Process S)
 * 4. Allostatic Load (McEwen chronic wear)
 * 5. Zeigarnik Wound Pressure (unresolved issues & rumination)
 * 6. Somatic Activation ("Butterflies" / anticipation)
 * 7. Active Ego Defense Intensity (Vaillant tier resistance)
 */
export class AtmosphericGestaltField extends PolygonalNetwork {

	constructor() {

		super( {
			order       : 7,
			name        : 'AtmosphericGestaltField',
			vertexNames : [
				'affectMagnitude',
				'interoceptiveTension',
				'circadianPressure',
				'allostaticWear',
				'zeigarnikTension',
				'somaticButterflies',
				'egoDefenseCharge',
			],
		} )

	}

	evaluate( {
		valence = 0,
		arousal = 0,
		dominance = 0,
		interoception = {},
		sleepDebt = 0,
		allostaticLoad = 0,
		unresolvedWounds = 0,
		butterflies = 0,
		defenseDirective = {},
		personality = {},
		attachmentStyle = 'secure',
		elapsedHours = 0,
		maskTension = 0,
		coRegulationStrain = 0,
	} = {} ) {

		const N = personality.neuroticism ?? 0.5
		const C = personality.conscientiousness ?? 0.5
		const O = personality.openness ?? 0.5
		const A = personality.agreeableness ?? 0.5
		const isAnxious = attachmentStyle === 'anxious' || attachmentStyle === 'anxious-preoccupied'
		const isAvoidant = attachmentStyle === 'avoidant' || attachmentStyle === 'dismissive-avoidant'

		// Neuroticism is the primary biological amplifier of felt psychic load
		const neuroticMultiplier = 0.6 + N * 1.2
		// Conscientiousness dampens chaotic psychic entropy
		const groundingDampener = 1.0 - C * 0.35

		// Bridge 2 ($R_3 + R_5 \rightarrow R_7$): Somatization of Social Incongruence & Autonomic Strain
		const maskSomatization = maskTension * 0.3 * neuroticMultiplier
		const vagalAllostaticWear = coRegulationStrain * 0.25 * neuroticMultiplier

		const v1_affectMag = clamp01( ( Math.sqrt( valence * valence + arousal * arousal + dominance * dominance ) / Math.sqrt( 3 ) ) * neuroticMultiplier )
		const rawIntero = ( ( ( interoception.narrowing ?? 0 ) + ( interoception.conductance ?? 0 ) ) / 2 ) * neuroticMultiplier
		const v2_interoception = clamp01( rawIntero + maskSomatization )
		const v3_circadian = clamp01( sleepDebt )
		const v4_allostasis = clamp01( ( allostaticLoad * neuroticMultiplier ) + vagalAllostaticWear )

		// Zeigarnik tension modulated by absence & rumination profile + mask unresolved residue
		let zeigarnikBase = unresolvedWounds * 0.25 + ( maskTension > 0.35 ? maskTension * 0.2 : 0 )
		if ( elapsedHours > 0 ) {

			if ( isAnxious || N > 0.6 ) {

				zeigarnikBase += Math.min( 0.4, ( elapsedHours / 12 ) * 0.2 * N ) // Absence festers

			}
			else if ( isAvoidant ) {

				zeigarnikBase *= Math.max( 0.5, 1 - ( elapsedHours / 48 ) * 0.3 ) // Avoidant repression

			}
			else if ( C > 0.7 && N < 0.3 ) {

				zeigarnikBase *= Math.max( 0.4, 1 - ( elapsedHours / 24 ) * 0.4 ) // Stoic cognitive resolution

			}

		}

		const v5_zeigarnik = clamp01( zeigarnikBase * neuroticMultiplier )
		const v6_butterflies = clamp01( butterflies * ( 0.7 + O * 0.6 ) )
		const v7_defense = clamp01( ( defenseDirective.active ? 0.75 : 0.1 ) + ( isAvoidant ? 0.25 : 0 ) )

		// Dynamic Personality Weights for 7 Vertices:
		// - Anxious Devotee: heavy weight on zeigarnik, interoception, and affect
		// - Stoic Sage: heavy weight on circadian, allostasis, and defense regulation
		// - Outlaw: heavy weight on ego-defense and affect magnitude
		const w1 = clamp01( 0.7 + N * 0.8 )
		const w2 = clamp01( 0.6 + N * 1.0 )
		const w3 = clamp01( 0.8 + C * 0.6 )
		const w4 = clamp01( 0.7 + ( 1 - C ) * 0.5 + N * 0.6 )
		const w5 = clamp01( 0.6 + ( isAnxious ? 1.0 : 0 ) + N * 0.8 )
		const w6 = clamp01( 0.5 + O * 0.8 + ( 1 - isAvoidant ? 0.4 : 0 ) )
		const w7 = clamp01( 0.6 + ( isAvoidant ? 0.9 : 0 ) + ( 1 - A ) * 0.6 )

		const vertices = [
			v1_affectMag,
			v2_interoception,
			v3_circadian,
			v4_allostasis,
			v5_zeigarnik,
			v6_butterflies,
			v7_defense,
		]
		const weights = [ w1, w2, w3, w4, w5, w6, w7 ]
		const metrics = this.calculateTensorMetrics( vertices, weights )

		// Psychological Density: weighted saturation of inner mental space
		const psychologicalDensity = clamp01( metrics.mean * neuroticMultiplier * groundingDampener )

		// Permeability: porous boundary vs hardened emotional shell (directly shaped by Openness)
		const permeability = clamp01( ( 1 - psychologicalDensity ) * 0.65 + O * 0.35 - ( isAvoidant ? 0.2 : 0 ) )

		let somaticPresence = 'grounded_lightness'
		if ( psychologicalDensity > 0.65 ) {

			somaticPresence = 'dense_saturation'

		}
		else if ( v6_butterflies > 0.55 && psychologicalDensity < 0.45 ) {

			somaticPresence = 'electric_anticipation'

		}
		else if ( v3_circadian > 0.65 || v4_allostasis > 0.6 ) {

			somaticPresence = 'weary_gravitas'

		}

		return {
			order : 7,
			psychologicalDensity,
			somaticPresence,
			permeability,
			vertices : {
				affectMagnitude      : v1_affectMag,
				interoceptiveTension : v2_interoception,
				circadianPressure    : v3_circadian,
				allostaticWear       : v4_allostasis,
				zeigarnikTension     : v5_zeigarnik,
				somaticButterflies   : v6_butterflies,
				egoDefenseCharge     : v7_defense,
			},
			weights : { w1, w2, w3, w4, w5, w6, w7 },
			metrics,
		}

	}

}

/**
 * Order 11 (Endecangulation): HolisticMoralAgencyNexus
 * The master existential arbiter combining all 11 fundamental human vectors:
 * 1. Core Beliefs Axioms (Immutable ethical foundation)
 * 2. Ego Health & Self-Respect
 * 3. Love-Hate Balance (LoveHateEngine net bond)
 * 4. Relational Power & Symmetry
 * 5. Moral Guilt & Reparation Pressure
 * 6. Betrayal Scar Floor (permanent distrust thresholds)
 * 7. Cultural Script Salience (honor, reciprocity, saving face)
 * 8. Big Five Personality Priors
 * 9. Autobiographical Narrative Chapter
 * 10. Mortality / Fragility Salience (TMT)
 * 11. Primary Panksepp Drives (Seeking/Care vs Panic/Rage)
 */
export class HolisticMoralAgencyNexus extends PolygonalNetwork {

	constructor() {

		super( {
			order       : 11,
			name        : 'HolisticMoralAgencyNexus',
			vertexNames : [
				'axiomaticIntegrity',
				'egoSelfRespect',
				'relationalBond',
				'relationalSymmetry',
				'guiltRemorse',
				'betrayalScar',
				'culturalDuty',
				'personalityPriors',
				'narrativeCoherence',
				'existentialFragility',
				'primaryTeleology',
			],
		} )

	}

	evaluate( {
		beliefConflictScore = 0,
		egoHealth = 1,
		netBond = 0,
		powerSymmetry = 0.5,
		guiltLevel = 0,
		hasBetrayalTrace = false,
		culturalDuty = 0.5,
		personality = {},
		narrativeCoherence = 0.8,
		mortalitySalience = 0,
		seekingDrive = 0.5,
		attachmentStyle = 'secure',
		elapsedHours = 0,
		psychologicalDensity = 0.5,
		somaticExhaustion = false,
	} = {} ) {

		const N = personality.neuroticism ?? 0.5
		const A = personality.agreeableness ?? 0.5
		const C = personality.conscientiousness ?? 0.5
		const O = personality.openness ?? 0.5
		const E = personality.extraversion ?? 0.5
		const isAnxious = attachmentStyle === 'anxious' || attachmentStyle === 'anxious-preoccupied'
		const isAvoidant = attachmentStyle === 'avoidant' || attachmentStyle === 'dismissive-avoidant'

		// 11 Vertices computed with personality refractions
		const v1_axiomatic = clamp01( 1 - beliefConflictScore )
		const v2_ego = clamp01( egoHealth * ( 0.6 + ( 1 - N ) * 0.4 + ( 1 - A ) * 0.4 ) )
		const v3_bond = clamp01( ( netBond + 1 ) / 2 )
		const v4_symmetry = clamp01( powerSymmetry )
		const v5_guilt = clamp01( guiltLevel * ( 0.5 + A * 0.8 + N * 0.6 ) )
		const v6_betrayal = hasBetrayalTrace ? clamp01( 0.85 + ( 1 - A ) * 0.15 + ( isAvoidant ? 0.1 : 0 ) ) : 0.05
		const v7_cultural = clamp01( culturalDuty * ( 0.7 + C * 0.6 ) )
		const v8_personality = clamp01( ( A + C + ( 1 - N ) ) / 3 )
		const v9_narrative = clamp01( narrativeCoherence * ( 0.6 + O * 0.5 + C * 0.3 ) )
		const v10_mortality = clamp01( mortalitySalience * ( 0.7 + N * 0.6 ) )
		const v11_drive = clamp01( seekingDrive * ( 0.6 + E * 0.5 + O * 0.4 ) )

		// 11-Dimensional Individual Adaptive Weight Tensor:
		// - Stoic Sage: high weight on axiomatic integrity (v1), narrative coherence (v9), low on reactive panic
		// - Anxious Devotee: massive weight on relational bond (v3) and guilt (v5), suppressed ego self-respect (v2)
		// - Streetwise Outlaw: dominant weight on ego self-respect (v2), power symmetry (v4), and betrayal scar (v6), near-zero on guilt (v5) and duty (v7)
		const w1 = clampWeight( 1.0 + C * 1.2 + O * 0.4 - ( isAnxious ? 0.3 : 0 ) )
		const w2 = clampWeight( 0.5 + ( 1 - N ) * 0.8 + ( 1 - A ) * 1.1 + ( isAvoidant ? 0.6 : 0 ) - ( isAnxious ? 0.4 : 0 ) )
		const w3 = clampWeight( 0.5 + A * 1.6 + ( isAnxious ? 1.2 : 0 ) - ( isAvoidant ? 0.8 : 0 ) )
		const w4 = clampWeight( 0.5 + ( 1 - A ) * 1.2 + C * 0.6 + ( isAvoidant ? 0.5 : 0 ) )
		const w5 = clampWeight( 0.2 + A * 1.3 + N * 1.1 - ( isAvoidant ? 0.8 : 0 ) )
		const w6 = clampWeight( 0.6 + ( 1 - A ) * 1.3 + ( isAvoidant ? 0.8 : 0 ) + N * 0.4 )
		const w7 = clampWeight( 0.4 + C * 0.8 + A * 0.4 )
		const w8 = 1.0
		const w9 = clampWeight( 0.6 + O * 0.9 + C * 0.7 )
		const w10 = clampWeight( 0.5 + N * 0.8 )
		const w11 = clampWeight( 0.5 + E * 0.7 + O * 0.5 )

		const vertices = [
			v1_axiomatic,
			v2_ego,
			v3_bond,
			v4_symmetry,
			v5_guilt,
			v6_betrayal,
			v7_cultural,
			v8_personality,
			v9_narrative,
			v10_mortality,
			v11_drive,
		]
		const weights = [ w1, w2, w3, w4, w5, w6, w7, w8, w9, w10, w11 ]
		const metrics = this.calculateTensorMetrics( vertices, weights )

		// Moral Equilibrium: weighted harmony across ethical axioms, ego health, narrative, and bond
		const positiveMoralCore = ( v1_axiomatic * w1 + v2_ego * w2 + v3_bond * w3 + v9_narrative * w9 ) / ( w1 + w2 + w3 + w9 )
		const traumaticStrain = ( v6_betrayal * w6 + v5_guilt * w5 ) / ( w6 + w5 )
		const moralEquilibrium = clamp01( positiveMoralCore * 0.75 - traumaticStrain * 0.35 + metrics.convergenceIndex * 0.25 )

		// Existential Clarity: non-linear synthesis of grounding, convergence, and narrative integrity
		const existentialClarity = clamp01( metrics.convergenceIndex * ( 0.5 + C * 0.3 + ( 1 - N ) * 0.3 ) )

		// Dynamic Emergent Ethical Posture:
		let ethicalPosture = 'balanced_reciprocity'

		if ( v6_betrayal > 0.6 ) {

			if ( isAvoidant || ( 1 - A ) > 0.6 ) {

				// Outlaw / Cynic posture under betrayal
				ethicalPosture = 'cynical_detachment'

			}
			else if ( isAnxious && v3_bond > 0.45 && v2_ego < 0.35 ) {

				// Anxious codependency: agonizing conflict between betrayal pain and fear of being left
				ethicalPosture = 'conflicted_appeasement'

			}
			else {

				// Stoic / Healthy boundary
				ethicalPosture = 'unyielding_boundary'

			}

		}
		else if ( v5_guilt > 0.55 && v3_bond > 0.4 && A >= 0.4 ) {

			ethicalPosture = 'humble_reparation'

		}
		else if ( v1_axiomatic < 0.45 ) {

			ethicalPosture = 'unyielding_boundary'

		}
		else if ( v3_bond > 0.75 && moralEquilibrium > 0.65 ) {

			ethicalPosture = isAnxious ? 'sacrificial_devotion' : 'compassionate_protection'

		}
		else if ( v10_mortality > 0.6 && C > 0.6 ) {

			ethicalPosture = 'philosophical_grace'

		}

		// Bridge 3 ($R_7 \rightarrow R_{11}$): Somatic Exhaustion Override
		// When biological density is overwhelming (>0.65 or dense_saturation),
		// high-cost moral grace collapses into boundary survival
		const isExhausted = somaticExhaustion || psychologicalDensity > 0.65
		if ( isExhausted ) {

			if ( ethicalPosture === 'philosophical_grace' || ethicalPosture === 'humble_reparation' ) {

				ethicalPosture = isAvoidant ? 'cynical_detachment' : 'unyielding_boundary'

			}

		}

		return {
			order : 11,
			moralEquilibrium,
			ethicalPosture,
			existentialClarity,
			vertices : {
				axiomaticIntegrity   : v1_axiomatic,
				egoSelfRespect       : v2_ego,
				relationalBond       : v3_bond,
				relationalSymmetry   : v4_symmetry,
				guiltRemorse         : v5_guilt,
				betrayalScar         : v6_betrayal,
				culturalDuty         : v7_cultural,
				personalityPriors    : v8_personality,
				narrativeCoherence   : v9_narrative,
				existentialFragility : v10_mortality,
				primaryTeleology     : v11_drive,
			},
			weights : { w1, w2, w3, w4, w5, w6, w7, w8, w9, w10, w11 },
			metrics,
		}

	}

}

/**
 * Unified Catalog aggregating and managing all polygonal convergence networks
 * with autopoietic cross-order resonance cascades.
 */
export class PolygonalTriangulationCatalog {

	constructor() {

		this.maskDetector = new AffectiveMaskDetector()
		this.coRegulation = new PolyvagalCoRegulationNetwork()
		this.atmosphericField = new AtmosphericGestaltField()
		this.moralNexus = new HolisticMoralAgencyNexus()

	}

	/**
	 * Evaluates all 4 polygonal networks through cascading autopoietic bridges
	 * from live EmotionsHypercartoon state.
	 * @param {Object} state - Compiled state inputs
	 * @returns {Object} Complete convergence report across orders 3, 5, 7, and 11.
	 */
	converge( state = {} ) {

		const personality = state.personality ?? {}
		const attachmentStyle = state.attachmentStyle ?? 'secure'
		const elapsedHours = state.elapsedHours ?? ( ( state.elapsedMs ?? 0 ) / 3600000 )

		// Step 1: Order 3 (Triangulation) — Mask & Authenticity Detection
		const triangulation = this.maskDetector.evaluate( {
			semanticValence   : state.semanticValence ?? state.valence ?? 0,
			inputLength       : state.inputLength ?? 0,
			recentWoundsCount : state.recentWoundsCount ?? 0,
			previousValence   : state.previousValence ?? 0,
			personality,
			attachmentStyle,
			elapsedHours,
		} )

		// Step 2: Order 5 (Pentangulation) — Bridge 1 (R3 -> R5) & Bridge 4 (R11 -> R5)
		const pentangulation = this.coRegulation.evaluate( {
			userArousal         : state.userArousal ?? state.arousal ?? 0.5,
			agentCortisol       : state.agentCortisol ?? state.cortisol ?? 0,
			netBond             : state.netBond ?? 0,
			repairsCount        : state.repairsCount ?? 0,
			decisionFatigue     : state.decisionFatigue ?? state.fatigue ?? 0,
			personality,
			attachmentStyle,
			elapsedHours,
			maskTension         : triangulation.maskIndex,
			isMaskDetected      : triangulation.maskDetected,
			topDownMoralPosture : state.previousMoralPosture ?? null,
		} )

		// Step 3: Order 7 (Heptangulation) — Bridge 2 (R3 + R5 -> R7)
		const coRegulationStrain = clamp01(
			( 1 - pentangulation.coRegulationCapacity ) +
			( pentangulation.directive === 'protective_boundary' ? 0.35 : 0 )
		)
		const heptangulation = this.atmosphericField.evaluate( {
			valence            : state.valence ?? 0,
			arousal            : state.arousal ?? 0,
			dominance          : state.dominance ?? 0,
			interoception      : state.interoception ?? {},
			sleepDebt          : state.sleepDebt ?? 0,
			allostaticLoad     : state.allostaticLoad ?? 0,
			unresolvedWounds   : state.unresolvedWounds ?? 0,
			butterflies        : state.butterflies ?? 0,
			defenseDirective   : state.defenseDirective ?? {},
			personality,
			attachmentStyle,
			elapsedHours,
			maskTension        : triangulation.maskIndex,
			coRegulationStrain,
		} )

		// Step 4: Order 11 (Endecangulation) — Bridge 3 (R7 -> R11)
		const isSomaticExhausted = heptangulation.psychologicalDensity > 0.65 ||
			heptangulation.somaticPresence === 'dense_saturation'
		const endecangulation = this.moralNexus.evaluate( {
			beliefConflictScore  : state.beliefConflictScore ?? 0,
			egoHealth            : state.egoHealth ?? 1,
			netBond              : state.netBond ?? 0,
			powerSymmetry        : state.powerSymmetry ?? 0.5,
			guiltLevel           : state.guiltLevel ?? 0,
			hasBetrayalTrace     : state.hasBetrayalTrace ?? false,
			culturalDuty         : state.culturalDuty ?? 0.5,
			personality,
			narrativeCoherence   : state.narrativeCoherence ?? 0.8,
			mortalitySalience    : state.mortalitySalience ?? 0,
			seekingDrive         : state.seekingDrive ?? 0.5,
			attachmentStyle,
			elapsedHours,
			psychologicalDensity : heptangulation.psychologicalDensity,
			somaticExhaustion    : isSomaticExhausted,
		} )

		// Step 5: Composite Blossomed Dynamics
		const isVisceralSuspicion = triangulation.maskDetected &&
			( heptangulation.vertices.interoceptiveTension > 0.35 || heptangulation.psychologicalDensity > 0.5 )
		const visceralSuspicionIntensity = isVisceralSuspicion
			? clamp01( triangulation.maskIndex * 0.6 + heptangulation.psychologicalDensity * 0.4 )
			: 0

		const isCompassionFatigue = isSomaticExhausted &&
			( endecangulation.ethicalPosture === 'unyielding_boundary' || endecangulation.ethicalPosture === 'cynical_detachment' ) &&
			( ( state.repairsCount ?? 0 ) > 0 || ( state.allostaticLoad ?? 0 ) > 0.2 || ( state.agentCortisol ?? 0 ) > 0.25 || ( state.decisionFatigue ?? 0 ) > 0.3 || ( state.fatigue ?? 0 ) > 0.3 )
		const compassionFatigueIntensity = isCompassionFatigue
			? clamp01( heptangulation.psychologicalDensity * 0.7 + ( state.allostaticLoad ?? 0.3 ) * 0.3 )
			: 0

		const isSacrificialTranscendence = endecangulation.ethicalPosture === 'sacrificial_devotion' &&
			heptangulation.psychologicalDensity > 0.55
		const sacrificialTranscendenceIntensity = isSacrificialTranscendence
			? clamp01( endecangulation.metrics.convergenceIndex * 0.7 + ( ( state.netBond ?? 0 ) + 1 ) * 0.15 )
			: 0

		this.lastReport = {
			triangulation, // Order 3
			pentangulation, // Order 5
			heptangulation, // Order 7
			endecangulation, // Order 11
			blossomedDynamics : {
				visceralSuspicion         : { active: isVisceralSuspicion, intensity: visceralSuspicionIntensity },
				compassionFatigue         : { active: isCompassionFatigue, intensity: compassionFatigueIntensity },
				sacrificialTranscendence  : { active: isSacrificialTranscendence, intensity: sacrificialTranscendenceIntensity },
			},
			summary : {
				maskDetected              : triangulation.maskDetected,
				coRegulationDirective     : pentangulation.directive,
				somaticPresence           : heptangulation.somaticPresence,
				ethicalPosture            : endecangulation.ethicalPosture,
				visceralSuspicionActive   : isVisceralSuspicion,
				compassionFatigueActive   : isCompassionFatigue,
				sacrificialTranscendenceActive : isSacrificialTranscendence,
				holisticClarity           : ( triangulation.metrics.convergenceIndex +
					pentangulation.metrics.convergenceIndex +
					heptangulation.metrics.convergenceIndex +
					endecangulation.metrics.convergenceIndex ) / 4,
			},
		}

		return this.lastReport

	}

	/**
	 * Returns a lightweight snapshot of current polygonal bridges and blossomed dynamics.
	 */
	getBridgeSnapshot() {

		if ( !this.lastReport ) return null
		return {
			blossomedDynamics : this.lastReport.blossomedDynamics,
			summary           : this.lastReport.summary,
		}

	}

}

