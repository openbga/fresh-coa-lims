"""The database guards of shelf-life evaluations.

An evaluation is never deleted and starts as a draft at revision 1. While it is a draft, what it
was drafted from (the protocol code, container closure, condition, specification version, test,
unit, acceptance criterion, drafter and drafting time) is fixed, and every change advances its
revision; once concluded or withdrawn it never changes. A study is linked to an evaluation or
unlinked only while the evaluation is a draft (the guard reads the evaluation under a share lock,
as the services lock it), and only a study of the evaluation's protocol code and container
closure; a link is never changed.
"""

from django.db import migrations

GUARD = """
CREATE FUNCTION stability_guard_shelf_life() RETURNS trigger AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'A shelf-life evaluation is never deleted';
  END IF;
  IF TG_OP = 'INSERT' THEN
    IF NEW.state <> 'draft' OR NEW.revision <> 1 THEN
      RAISE EXCEPTION 'A shelf-life evaluation starts as a draft at revision 1';
    END IF;
    RETURN NEW;
  END IF;
  IF OLD.state <> 'draft' THEN
    RAISE EXCEPTION 'A concluded or withdrawn shelf-life evaluation never changes';
  END IF;
  IF (to_jsonb(OLD) - 'direction' - 'purpose' - 'state' - 'outcome' - 'shelf_life_months'
        - 'conclusion' - 'concluded_at' - 'content' - 'content_hash' - 'withdrawn_at'
        - 'revision')
     IS DISTINCT FROM
     (to_jsonb(NEW) - 'direction' - 'purpose' - 'state' - 'outcome' - 'shelf_life_months'
        - 'conclusion' - 'concluded_at' - 'content' - 'content_hash' - 'withdrawn_at'
        - 'revision') THEN
    RAISE EXCEPTION 'What a shelf-life evaluation was drafted from is fixed';
  END IF;
  IF NEW.revision <= OLD.revision THEN
    RAISE EXCEPTION 'A change of a shelf-life evaluation advances its revision';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER stability_shelf_life_guard
  BEFORE INSERT OR UPDATE OR DELETE ON stability_shelflifeevaluation
  FOR EACH ROW EXECUTE FUNCTION stability_guard_shelf_life();

CREATE FUNCTION stability_guard_shelf_life_study() RETURNS trigger AS $$
DECLARE
  parent stability_shelflifeevaluation%ROWTYPE;
  link stability_shelflifestudy%ROWTYPE;
BEGIN
  IF TG_OP = 'UPDATE' THEN
    RAISE EXCEPTION 'A study of a shelf-life evaluation is linked or unlinked, never changed';
  END IF;
  IF TG_OP = 'DELETE' THEN
    link := OLD;
  ELSE
    link := NEW;
  END IF;
  SELECT * INTO parent FROM stability_shelflifeevaluation
    WHERE id = link.evaluation_id FOR SHARE;
  IF parent.state IS DISTINCT FROM 'draft' THEN
    RAISE EXCEPTION 'The studies of a shelf-life evaluation change only while it is a draft';
  END IF;
  IF TG_OP = 'INSERT' AND NOT EXISTS (
    SELECT 1 FROM stability_study s
      JOIN stability_protocol p ON p.id = s.protocol_id
    WHERE s.id = NEW.study_id AND p.code = parent.protocol_code
      AND s.container_closure = parent.container_closure
  ) THEN
    RAISE EXCEPTION 'A shelf-life evaluation uses studies of its protocol and container closure';
  END IF;
  IF TG_OP = 'DELETE' THEN
    RETURN OLD;
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER stability_shelf_life_study_guard
  BEFORE INSERT OR UPDATE OR DELETE ON stability_shelflifestudy
  FOR EACH ROW EXECUTE FUNCTION stability_guard_shelf_life_study();
"""
GUARD_REVERSE = """
DROP TRIGGER stability_shelf_life_study_guard ON stability_shelflifestudy;
DROP FUNCTION stability_guard_shelf_life_study();
DROP TRIGGER stability_shelf_life_guard ON stability_shelflifeevaluation;
DROP FUNCTION stability_guard_shelf_life();
"""


class Migration(migrations.Migration):
    dependencies = [("stability", "0006_shelf_life_evaluation")]

    operations = [migrations.RunSQL(GUARD, GUARD_REVERSE)]
