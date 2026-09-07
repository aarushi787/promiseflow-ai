# Industry and domain extension boundaries

The implemented synthetic automotive example is configuration: resources, routings, approved alternatives, fixtures and suppliers. No CNC branch exists in the solver. Fabrication can be represented using laser/bending/welding/inspection resources and typed linear routing inputs. A pack installer and validated second demo are not yet implemented; the Settings selection currently labels the configuration and does not replace data.

Future pack files should define terminology, allowed resource/operation categories, templates and additional validation while normalizing to Factory. Domain adapters should remain separate: production/sales promise, maintenance impact and supply impact already use the shared engine; workforce strategy, CAPEX and energy are future domains.

Do not label food/pharma supported where sequence-dependent cleaning, vessel batching or release controls are mandatory. Energy/carbon fields cannot justify estimates without measured input. Alternative materials/routes/suppliers must be explicitly approved in the canonical model before a solver can choose them.
