"""Draft synthetic specification/method/sampling profiles for the five manufacturing segments.

Every record is an editable draft that a different quality approver must review and sign. Values are
illustrative only: they are not regulatory limits, complete test panels or validated methods.
"""

from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from catalog import services as catalog
from catalog.models import Material, Method, Specification
from core.models import AuditEvent
from sampling import services as sampling
from sampling.models import SamplingPlan

# Methods that run in a QC batch, with illustrative batch QC checks (synthetic limits).
BATCH_QC = {
    "hplc-assay": [
        ("blank", "Reagent blank", "%", None, "0.05"),
        ("control", "Control standard recovery", "%", "98.0", "102.0"),
    ],
    "gc-purity": [("control", "Reference standard purity", "%", "99.0", "101.0")],
}

# Methods whose result is calculated from raw measurements, and whether each result must record
# an instrument and a reagent or standard lot. The formulas are synthetic examples.
CALCULATIONS = {
    "kf-water": {
        "inputs": [
            ("titrant_volume", "Titrant volume", "mL"),
            ("titer", "Titrant water equivalent", "mg/mL"),
            ("sample_mass", "Sample mass", "mg"),
        ],
        "formula": "titrant_volume * titer / sample_mass * 100",
        "unit": "% w/w",
        "decimals": 2,
        "requires_equipment": True,
        "requires_reagent": True,
    },
    "loss-on-drying": {
        "inputs": [
            ("mass_before", "Sample mass before drying", "g"),
            ("mass_after", "Sample mass after drying", "g"),
        ],
        "formula": "(mass_before - mass_after) / mass_before * 100",
        "unit": "%",
        "decimals": 2,
        "requires_equipment": True,
        "requires_reagent": False,
    },
}

REASON = "Synthetic segment profile; quality-owner applicability review required."

METHODS = {
    "ftir-identity": ("Identity by infrared spectroscopy", "FTIR"),
    "hplc-assay": ("Assay by liquid chromatography", "HPLC-UV"),
    "kf-water": ("Water by Karl Fischer titration", "KF titration"),
    "hptlc-identity": ("Botanical identity by HPTLC fingerprint", "HPTLC"),
    "icpms-lead": ("Lead by ICP-MS", "ICP-MS"),
    "micro-tamc": ("Total aerobic microbial count", "Plate count"),
    "micro-salmonella": ("Salmonella detection", "Enrichment and confirmation"),
    "organoleptic": ("Appearance, odour and taste against standard", "Sensory"),
    "loss-on-drying": ("Moisture by loss on drying", "Gravimetric"),
    "gc-purity": ("Purity by gas chromatography", "GC-FID"),
    "visual-inspection": ("Visual inspection against drawing", "Visual"),
    "caliper-dimension": ("Critical dimension by caliper", "Dimensional"),
    "tensile-force": ("Tensile break force", "Universal tester"),
}


def numeric(code, name, method, unit, low=None, high=None, decimals=None, result_type="numeric"):
    return {
        "code": code,
        "name": name,
        "method": method,
        "result_type": result_type,
        "unit": unit,
        "lower_limit": Decimal(low) if low else None,
        "upper_limit": Decimal(high) if high else None,
        "reporting_decimals": decimals,
    }


def qualitative(code, name, method, criterion, expected="conforms"):
    return {
        "code": code,
        "name": name,
        "method": method,
        "result_type": "qualitative",
        "expected_result": expected,
        "expected_text": criterion,
    }


PROFILES = [
    {
        "segment": "pharma",
        "material": ("syn-api-pharma", "Synthetic active ingredient A", "raw_material"),
        "stage": "incoming",
        "tests": [
            qualitative("identity", "Identity", "ftir-identity", "Conforms to reference"),
            {
                **numeric(
                    "assay", "Assay (dried basis)", "hplc-assay", "% w/w", "98.0", "102.0", 1
                ),
                "replicates": 2,
                "max_retests": 1,
            },
            numeric("water", "Water", "kf-water", "% w/w", high="0.5", decimals=1),
        ],
        "plan": {"basis": "sqrt_plus_one", "minimum_quantity": Decimal("20"), "unit": "g"},
    },
    {
        "segment": "supplement",
        "material": ("syn-botanical", "Synthetic botanical powder", "raw_material"),
        "stage": "incoming",
        "tests": [
            qualitative(
                "identity", "Botanical identity", "hptlc-identity", "Conforms to reference"
            ),
            numeric("lead", "Lead", "icpms-lead", "µg/g", high="1.0", decimals=1),
            numeric(
                "tamc",
                "Total aerobic count",
                "micro-tamc",
                "CFU/g",
                high="10000",
                decimals=0,
                result_type="count",
            ),
        ],
        "plan": {
            "basis": "fixed",
            "parameter": Decimal("3"),
            "minimum_quantity": Decimal("100"),
            "unit": "g",
        },
    },
    {
        "segment": "food",
        "material": ("syn-snack-bar", "Synthetic cereal bar", "finished_product"),
        "stage": "finished",
        "tests": [
            qualitative("identity", "Appearance and sensory", "organoleptic", "Conforms"),
            qualitative(
                "salmonella", "Salmonella", "micro-salmonella", "Not detected in 25 g", "absent"
            ),
            numeric("moisture", "Moisture", "loss-on-drying", "%", high="12.0", decimals=1),
        ],
        "plan": {
            "basis": "fixed",
            "parameter": Decimal("5"),
            "minimum_quantity": Decimal("10"),
            "unit": "units",
        },
    },
    {
        "segment": "chemical",
        "material": ("syn-solvent", "Synthetic solvent, technical grade", "finished_product"),
        "stage": "finished",
        "tests": [
            qualitative("identity", "Identity", "ftir-identity", "Conforms to reference"),
            numeric("purity", "Purity", "gc-purity", "%", low="99.5", decimals=1),
            numeric("water", "Water", "kf-water", "% w/w", high="0.05", decimals=2),
        ],
        "plan": {
            "basis": "percent",
            "parameter": Decimal("10"),
            "minimum_quantity": Decimal("1"),
            "unit": "L",
        },
    },
    {
        "segment": "device",
        "material": ("syn-housing", "Synthetic moulded housing", "component"),
        "stage": "incoming",
        "tests": [
            qualitative("identity", "Part and drawing revision", "visual-inspection", "Matches"),
            numeric("length", "Critical length", "caliper-dimension", "mm", "9.95", "10.05", 2),
            numeric(
                "break-force", "Tensile break force", "tensile-force", "N", low="50", decimals=1
            ),
        ],
        "plan": {
            "basis": "fixed",
            "parameter": Decimal("8"),
            "minimum_quantity": Decimal("8"),
            "unit": "units",
        },
    },
]


class Command(BaseCommand):
    help = "Create draft synthetic QC profiles for five segments; never approves anything."

    def add_arguments(self, parser):
        parser.add_argument("--actor", required=True, help="Quality user who authors the drafts.")

    def preflight(self):
        """Refuse to touch any existing record this command did not create.

        A code is reused only when its creation audit event carries this command's reason, so
        unrelated controlled evidence with a colliding code is never adopted or extended.
        """

        def seeded(obj, action):
            return AuditEvent.objects.filter(
                action=action,
                object_type=obj._meta.label_lower,
                object_id=str(obj.pk),
                reason=REASON,
            ).exists()

        collisions = []
        for method in Method.objects.filter(code__in=METHODS):
            if not seeded(method, "method.created"):
                collisions.append(f"method {method.code}")
        for profile in PROFILES:
            code = profile["material"][0]
            material = Material.objects.filter(code=code).first()
            spec_code = f"{code}-{profile['stage']}"
            plan_code = f"{spec_code}-plan"
            if material is not None:
                spec = Specification.objects.filter(code=spec_code, material=material).first()
                plan = SamplingPlan.objects.filter(code=plan_code, material=material).first()
                if not (
                    seeded(material, "material.created")
                    and spec is not None
                    and seeded(spec, "specification.created")
                    and plan is not None
                    and seeded(plan, "sampling_plan.created")
                ):
                    collisions.append(f"material {code} (or its specification/plan)")
                continue
            if Specification.objects.filter(code=spec_code).exists():
                collisions.append(f"specification {spec_code}")
            if SamplingPlan.objects.filter(code=plan_code).exists():
                collisions.append(f"sampling plan {plan_code}")
        if collisions:
            raise CommandError(
                "Existing records not created by this command use seed codes: "
                + ", ".join(collisions)
                + ". Nothing was created."
            )

    @transaction.atomic
    def handle(self, *args, **options):
        actor = get_user_model().objects.get(username=options["actor"])
        self.preflight()
        start = timezone.now()
        window = {"effective_from": start, "effective_until": start + timedelta(days=365)}
        methods = {}
        for code, (title, technique) in METHODS.items():
            method = Method.objects.filter(code=code).first()
            calculation = CALCULATIONS.get(code)
            if method is None:
                method, _ = catalog.create_method(
                    actor=actor,
                    code=code,
                    title=title,
                    technique=technique,
                    document_ref=f"SOP-SYN-{code.upper()} rev 1",
                    suitability_kind="validation",
                    suitability_ref=f"VAL-SYN-{code.upper()}",
                    summary="Synthetic placeholder procedure.",
                    requires_batch=code in BATCH_QC,
                    requires_equipment=bool(calculation and calculation["requires_equipment"]),
                    requires_reagent=bool(calculation and calculation["requires_reagent"]),
                    reason=REASON,
                    **window,
                )
                revision = method.revisions.get()
                if calculation:
                    for name, label, unit in calculation["inputs"]:
                        catalog.add_calculation_input(
                            actor=actor,
                            revision=revision,
                            reason=REASON,
                            code=name,
                            name=label,
                            unit=unit,
                        )
                    catalog.set_calculation(
                        actor=actor,
                        revision=revision,
                        reason=REASON,
                        formula=calculation["formula"],
                        unit=calculation["unit"],
                        decimals=calculation["decimals"],
                    )
                for check, name, unit, low, high in BATCH_QC.get(code, []):
                    catalog.add_qc_check(
                        actor=actor,
                        revision=revision,
                        reason=REASON,
                        code=check,
                        name=name,
                        unit=unit,
                        lower_limit=Decimal(low) if low else None,
                        upper_limit=Decimal(high) if high else None,
                    )
            methods[code] = method
        created = 0
        for profile in PROFILES:
            code, name, kind = profile["material"]
            if Material.objects.filter(code=code).exists():
                continue
            material = catalog.create_material(
                actor=actor, code=code, name=name, kind=kind, reason=REASON
            )
            _, revision = catalog.create_specification(
                actor=actor,
                code=f"{code}-{profile['stage']}",
                title=f"{name} ({profile['segment']} example)",
                material=material,
                stage=profile["stage"],
                scope="general",
                basis="Synthetic illustrative limits; not a regulatory or compendial requirement.",
                reason=REASON,
                **window,
            )
            for position, line in enumerate(profile["tests"], start=1):
                catalog.add_test_line(
                    actor=actor,
                    revision=revision,
                    reason=REASON,
                    position=position,
                    **{**line, "method": methods[line["method"]]},
                )
            plan = profile["plan"]
            sampling.create_plan(
                actor=actor,
                code=f"{code}-{profile['stage']}-plan",
                title=f"{name} sampling ({profile['segment']} example)",
                material=material,
                stage=profile["stage"],
                basis=plan["basis"],
                parameter=plan.get("parameter"),
                minimum_quantity=plan["minimum_quantity"],
                quantity_unit=plan["unit"],
                instructions="Synthetic instructions: sample with clean tools; label each portion.",
                rationale="Synthetic example; the quality owner must justify representativeness.",
                reason=REASON,
                **window,
            )
            created += 1
        self.stdout.write(
            f"{created} draft segment profile(s) created. Another quality approver must review "
            "and sign each method, specification and sampling plan before use."
        )
