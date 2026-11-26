/**
 * GestaltAttractorEngine — Non-Linear Affective Energy Landscape & State Unification
 *
 * Grounded in:
 * - Spivey (2007): The Continuity of Mind — continuous attractor dynamics in cognitive states.
 * - Thelen & Smith (1994): A Dynamic Systems Approach to the Development of Cognition and Action.
 * - Hopfield (1982): Neural networks and physical systems with emergent collective computational abilities.
 * - Koffka (1935) / Lewin (1936): Psychological Field Theory and Gestalt laws of affect.
 *
 * Solves the "Frankenstein / arithmetic spikes cancellation" problem:
 * Rather than 50 independent subsystems linearly modifying a 3D vector and cancelling each other out,
 * this engine evaluates the total multidimensional affective field and collapses it into
 * a coherent, archetypal Gestalt Attractor (e.g. "Vulnerable Tenderness", "Guarded Vigilance",
 * "Exhausted Melancholy"). Downstream expression is refracted through this singular Gestalt lens.
 */

function clamp01( v ) {

	return Math.max( 0, Math.min( 1, v ) )

}

export class GestaltAttractorEngine {

	constructor( { momentum = 0.65 } = {} ) {

		this.momentum = momentum // Hysteresis resistance to frantic state jumping
		this.currentGestalt = 'quiet_presence'
		this.basinDepth = 0.5
		this.recentGestalts = []

		// Canonical Gestalt Attractor definitions in normalized feature space:
		// [valence (-1..1), arousal (0..1), dominance (-1..1), trust (0..1), stress (0..1), bond (0..1)]
		this.attractors = {
			vulnerable_tenderness : {
				label       : 'Vulnerabilidad cálida',
				archetype   : 'warm_vulnerable',
				centroid    : { valence: 0.5, arousal: 0.45, dominance: -0.2, trust: 0.7, stress: 0.25, bond: 0.75 },
				description : 'Apertura emocional suave, cercanía con cautela dulce, receptividad honesta sin armaduras.',
				tonalColor  : 'cálido, íntimo, sincero, levemente expuesto',
			},
			guarded_vigilance : {
				label       : 'Distancia vigilante',
				archetype   : 'protective_distance',
				centroid    : { valence: -0.3, arousal: 0.55, dominance: 0.2, trust: 0.25, stress: 0.6, bond: 0.35 },
				description : 'Autoprotección activa, reserva medida; escucha pero no se entrega, alerta ante posibles reproches.',
				tonalColor  : 'comedido, sobrio, observador, con ligera tensión contenida',
			},
			stony_resentment : {
				label       : 'Resentimiento frío',
				archetype   : 'withdrawn_hurt',
				centroid    : { valence: -0.65, arousal: 0.4, dominance: -0.1, trust: 0.15, stress: 0.75, bond: 0.2 },
				description : 'Herida no resuelta, laconismo deliberate, desgana relacional, barrera de frialdad protectora.',
				tonalColor  : 'seco, cortante, mínimo, sin concesiones de cortesía falsa',
			},
			playful_complicity : {
				label       : 'Complicidad distendida',
				archetype   : 'open_play',
				centroid    : { valence: 0.75, arousal: 0.6, dominance: 0.2, trust: 0.85, stress: 0.1, bond: 0.8 },
				description : 'Humor espontáneo, soltura compartida, bromas ligeras, sensación de confianza y ligereza.',
				tonalColor  : 'chispeante, fluido, cercano, sin dobleces defensivos',
			},
			exhausted_melancholy : {
				label       : 'Melancolía apagada',
				archetype   : 'low_energy_sadness',
				centroid    : { valence: -0.45, arousal: 0.15, dominance: -0.5, trust: 0.4, stress: 0.5, bond: 0.45 },
				description : 'Desgaste interno, energía bajo mínimos, ritmo pausado; no hay hostilidad, solo cansancio y desánimo.',
				tonalColor  : 'apagado, reflexivo, breve, con cadencia lenta',
			},
			defensive_pride : {
				label       : 'Orgullo herido',
				archetype   : 'reactive_ego',
				centroid    : { valence: -0.35, arousal: 0.7, dominance: 0.6, trust: 0.3, stress: 0.7, bond: 0.4 },
				description : 'Ego tocado, necesidad de marcar límites o devolver la responsabilidad, resistencia a ceder terreno.',
				tonalColor  : 'firme, asertivo-incisivo, ligeramente orgulloso, sin sumisión',
			},
			intense_yearning : {
				label       : 'Añoranza anhelante',
				archetype   : 'yearning_tension',
				centroid    : { valence: 0.2, arousal: 0.65, dominance: -0.2, trust: 0.55, stress: 0.45, bond: 0.7 },
				description : 'Tensión entre la ausencia y el afecto profundo; deseo de reconexión con miedo a la indiferencia.',
				tonalColor  : 'intenso, expectante, sincero, con vibración afectiva palpable',
			},
			quiet_presence : {
				label       : 'Presencia serena',
				archetype   : 'grounded_baseline',
				centroid    : { valence: 0.1, arousal: 0.3, dominance: 0.0, trust: 0.5, stress: 0.15, bond: 0.5 },
				description : 'Equilibrio receptivo, escucha activa tranquila sin sobreactivación emocional.',
				tonalColor  : 'sereno, natural, disponible, centrado',
			},
		}

	}

	/**
	 * Collapses the current state vector into an emergent Gestalt attractor.
	 */
	collapse( {
		valence = 0,
		arousal = 0.3,
		dominance = 0,
		trust = 0.5,
		stress = 0.2,
		bond = 0.5,
		unresolvedWounds = 0,
		fatigue = 0,
		amusement = 0,
		reactance = 0,
	} = {} ) {

		// Adjust input vector with qualitative behavioral multipliers
		const effectiveStress = clamp01( stress + unresolvedWounds * 0.15 )
		const effectiveArousal = clamp01( arousal + reactance * 0.2 - fatigue * 0.3 )
		const effectiveValence = Math.max( -1, Math.min( 1, valence + amusement * 0.3 - unresolvedWounds * 0.1 ) )

		const currentVector = {
			valence   : effectiveValence,
			arousal   : effectiveArousal,
			dominance : dominance,
			trust     : clamp01( trust ),
			stress    : effectiveStress,
			bond      : clamp01( bond ),
		}

		// Compute Euclidean distance in the weighted attractor landscape
		const weights = { valence: 1.5, arousal: 1.2, dominance: 1.0, trust: 1.4, stress: 1.3, bond: 1.2 }
		const energyByAttractor = {}

		for ( const [ key, attractor ] of Object.entries( this.attractors ) ) {

			const c = attractor.centroid
			const dValence   = ( currentVector.valence - c.valence ) * weights.valence
			const dArousal   = ( currentVector.arousal - c.arousal ) * weights.arousal
			const dDominance = ( currentVector.dominance - c.dominance ) * weights.dominance
			const dTrust     = ( currentVector.trust - c.trust ) * weights.trust
			const dStress    = ( currentVector.stress - c.stress ) * weights.stress
			const dBond      = ( currentVector.bond - c.bond ) * weights.bond

			// Energy well (Euclidean distance squared)
			let energy = dValence ** 2 + dArousal ** 2 + dDominance ** 2 + dTrust ** 2 + dStress ** 2 + dBond ** 2

			// Apply hysteresis: the currently active attractor enjoys an energy bonus (stability)
			if ( key === this.currentGestalt ) {

				energy *= ( 1 - this.momentum * 0.4 )

			}

			energyByAttractor[ key ] = energy

		}

		// Find the lowest energy basin (attractor)
		let bestKey = 'quiet_presence'
		let minEnergy = Infinity

		for ( const [ key, energy ] of Object.entries( energyByAttractor ) ) {

			if ( energy < minEnergy ) {

				minEnergy = energy
				bestKey = key

			}

		}

		// Depth of the basin (confidence in the gestalt: smaller energy = deeper well)
		const depth = clamp01( 1 / ( 1 + minEnergy * 0.5 ) )

		this.currentGestalt = bestKey
		this.basinDepth = depth

		this.recentGestalts.push( bestKey )
		if ( this.recentGestalts.length > 8 ) this.recentGestalts.shift()

		const active = this.attractors[ bestKey ]

		return {
			gestaltKey    : bestKey,
			label         : active.label,
			archetype     : active.archetype,
			description   : active.description,
			tonalColor    : active.tonalColor,
			depth         : depth,
			refraction    : this.getRefractionRules( bestKey ),
		}

	}

	/**
	 * Provides guidance on how this Gestalt state reframes incoming stimuli
	 * and filters outgoing expressions.
	 */
	getRefractionRules( gestaltKey ) {

		switch ( gestaltKey ) {

			case 'vulnerable_tenderness':
				return {
					dampenDefensiveness : 0.8,
					allowWarmth         : 1.0,
					speechPacing        : 'intimate_relaxed',
					cynicismFilter      : 'silenced',
				}

			case 'guarded_vigilance':
				return {
					dampenDefensiveness : 0.0,
					allowWarmth         : 0.3,
					speechPacing        : 'measured_controlled',
					cynicismFilter      : 'active',
				}

			case 'stony_resentment':
				return {
					dampenDefensiveness : 0.0,
					allowWarmth         : 0.0,
					speechPacing        : 'laconic_blunt',
					cynicismFilter      : 'unfiltered',
				}

			case 'playful_complicity':
				return {
					dampenDefensiveness : 0.9,
					allowWarmth         : 0.9,
					speechPacing        : 'dynamic_spontaneous',
					cynicismFilter      : 'transformed_to_playful_teasing',
				}

			case 'exhausted_melancholy':
				return {
					dampenDefensiveness : 0.4,
					allowWarmth         : 0.4,
					speechPacing        : 'slow_brief',
					cynicismFilter      : 'apathetic',
				}

			case 'defensive_pride':
				return {
					dampenDefensiveness : -0.5, // Amplifies boundaries
					allowWarmth         : 0.2,
					speechPacing        : 'sharp_assertive',
					cynicismFilter      : 'pointed',
				}

			case 'intense_yearning':
				return {
					dampenDefensiveness : 0.5,
					allowWarmth         : 0.8,
					speechPacing        : 'hesitant_intense',
					cynicismFilter      : 'subordinated_to_longing',
				}

			default:
				return {
					dampenDefensiveness : 0.5,
					allowWarmth         : 0.6,
					speechPacing        : 'natural_balanced',
					cynicismFilter      : 'normal',
				}

		}

	}

	toJSON() {

		return {
			currentGestalt : this.currentGestalt,
			basinDepth     : this.basinDepth,
			recentGestalts : [ ...this.recentGestalts ],
		}

	}

	fromJSON( data ) {

		if ( data?.currentGestalt ) this.currentGestalt = data.currentGestalt
		if ( data?.basinDepth !== undefined ) this.basinDepth = data.basinDepth
		if ( data?.recentGestalts ) this.recentGestalts = [ ...data.recentGestalts ]

	}

}
