"""The database guards of trend charts, limits versions and out-of-trend evaluations.

A chart is never changed or deleted. A limits version is never deleted and starts as a draft at
revision 1; while it is a draft its figures change with each saved revision, approval sets only
its state, approval time and frozen content, and once approved only ``superseded_at`` is set,
once, and not earlier than five minutes before the transaction that sets it (the application's
clock sets it; the allowance covers a difference between the two clocks). An evaluation is never
deleted, starts open at revision 1 and never changes once concluded; while open, its chart and
opener are fixed and every change advances its revision. An alert row is added only while its
evaluation is open (the guard reads the evaluation under a share lock, as the services lock it),
for a test of a lot with the chart's test code and an approved limits version of the same chart,
and is never changed or removed.
"""

from django.db import migrations

GUARD = """
CREATE FUNCTION trending_guard_chart() RETURNS trigger AS $$
BEGIN
  RAISE EXCEPTION 'A trend chart is never changed or deleted';
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER trending_chart_guard
  BEFORE UPDATE OR DELETE ON trending_chart
  FOR EACH ROW EXECUTE FUNCTION trending_guard_chart();

CREATE FUNCTION trending_guard_limits() RETURNS trigger AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'A limits version is never deleted';
  END IF;
  IF TG_OP = 'INSERT' THEN
    IF NEW.state <> 'draft' OR NEW.revision <> 1 THEN
      RAISE EXCEPTION 'A limits version starts as a draft at revision 1';
    END IF;
    RETURN NEW;
  END IF;
  IF NEW.chart_id <> OLD.chart_id OR NEW.version <> OLD.version
     OR NEW.drafted_by_id <> OLD.drafted_by_id OR NEW.drafted_at <> OLD.drafted_at THEN
    RAISE EXCEPTION 'The chart, version and drafter of a limits version are fixed';
  END IF;
  IF OLD.state = 'draft' AND NEW.state = 'draft' AND NEW.revision > OLD.revision THEN
    RETURN NEW;
  END IF;
  IF OLD.state = 'draft' AND NEW.state = 'approved' AND NEW.revision > OLD.revision
     AND (to_jsonb(OLD) - 'state' - 'revision' - 'approved_at' - 'content' - 'content_hash')
         = (to_jsonb(NEW) - 'state' - 'revision' - 'approved_at' - 'content' - 'content_hash') THEN
    RETURN NEW;
  END IF;
  IF OLD.state = 'approved' AND OLD.superseded_at IS NULL AND NEW.superseded_at >= now() - interval '5 minutes'
     AND (to_jsonb(OLD) - 'superseded_at') = (to_jsonb(NEW) - 'superseded_at') THEN
    RETURN NEW;
  END IF;
  RAISE EXCEPTION 'An approved limits version keeps what was approved; a draft changes with a new revision';
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER trending_limits_guard
  BEFORE INSERT OR UPDATE OR DELETE ON trending_limits
  FOR EACH ROW EXECUTE FUNCTION trending_guard_limits();

CREATE FUNCTION trending_guard_evaluation() RETURNS trigger AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'An out-of-trend evaluation is never deleted';
  END IF;
  IF TG_OP = 'INSERT' THEN
    IF NEW.state <> 'open' OR NEW.revision <> 1 THEN
      RAISE EXCEPTION 'An out-of-trend evaluation starts open at revision 1';
    END IF;
    RETURN NEW;
  END IF;
  IF OLD.state <> 'open' THEN
    RAISE EXCEPTION 'A concluded out-of-trend evaluation never changes';
  END IF;
  IF NEW.chart_id <> OLD.chart_id OR NEW.opened_by_id <> OLD.opened_by_id
     OR NEW.opened_at <> OLD.opened_at THEN
    RAISE EXCEPTION 'The chart and the opener of an evaluation are fixed';
  END IF;
  IF NEW.revision <= OLD.revision THEN
    RAISE EXCEPTION 'A change of an evaluation advances its revision';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER trending_evaluation_guard
  BEFORE INSERT OR UPDATE OR DELETE ON trending_evaluation
  FOR EACH ROW EXECUTE FUNCTION trending_guard_evaluation();

CREATE FUNCTION trending_guard_evaluation_alert() RETURNS trigger AS $$
DECLARE
  parent_state text;
  parent_chart bigint;
BEGIN
  IF TG_OP <> 'INSERT' THEN
    RAISE EXCEPTION 'An alert of an evaluation is never changed or removed';
  END IF;
  SELECT state, chart_id INTO parent_state, parent_chart FROM trending_evaluation
    WHERE id = NEW.evaluation_id FOR SHARE;
  IF parent_state IS DISTINCT FROM 'open' THEN
    RAISE EXCEPTION 'Alerts are added only while the evaluation is open';
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM trending_limits l
      JOIN trending_chart c ON c.id = l.chart_id
      JOIN analytical_analyticaltest t ON t.id = NEW.test_id
    WHERE l.id = NEW.limits_id AND l.chart_id = parent_chart AND l.state = 'approved'
      AND t.lot_id IS NOT NULL AND t.test_code = c.test_code
  ) THEN
    RAISE EXCEPTION 'An alert names a test of a lot and an approved limits version of its evaluation''s chart';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER trending_evaluation_alert_guard
  BEFORE INSERT OR UPDATE OR DELETE ON trending_evaluationalert
  FOR EACH ROW EXECUTE FUNCTION trending_guard_evaluation_alert();
"""
GUARD_REVERSE = """
DROP TRIGGER trending_evaluation_alert_guard ON trending_evaluationalert;
DROP FUNCTION trending_guard_evaluation_alert();
DROP TRIGGER trending_evaluation_guard ON trending_evaluation;
DROP FUNCTION trending_guard_evaluation();
DROP TRIGGER trending_limits_guard ON trending_limits;
DROP FUNCTION trending_guard_limits();
DROP TRIGGER trending_chart_guard ON trending_chart;
DROP FUNCTION trending_guard_chart();
"""


class Migration(migrations.Migration):
    dependencies = [("trending", "0001_initial"), ("analytical", "0013_review_evidence")]

    operations = [migrations.RunSQL(GUARD, GUARD_REVERSE)]
