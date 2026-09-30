from tradutor_pdf.ui.utils import MovingAverageEstimator, format_eta


def test_format_eta():
    assert format_eta(None) == ""
    assert format_eta(0) == "concluído"
    assert format_eta(-5) == "concluído"
    assert format_eta(30) == "~30 s"
    assert format_eta(59.4) == "~59 s"
    assert format_eta(60) == "~1 min"
    assert format_eta(75) == "~1 min 15 s"
    assert format_eta(3599) == "~59 min 59 s"
    assert format_eta(3600) == "~1 h"
    assert format_eta(3665) == "~1 h 1 min"
    assert format_eta(7320) == "~2 h 2 min"


def test_moving_average_estimator():
    estimator = MovingAverageEstimator(window_size=3)
    assert estimator.average_duration is None
    assert estimator.estimate_remaining(10) is None
    assert estimator.estimate_remaining(0) == 0.0

    estimator.record(2.0)
    assert estimator.average_duration == 2.0
    assert estimator.estimate_remaining(5) == 10.0

    estimator.record(4.0)
    assert estimator.average_duration == 3.0
    assert estimator.estimate_remaining(5) == 15.0

    estimator.record(6.0)
    assert estimator.average_duration == 4.0
    assert estimator.estimate_remaining(2) == 8.0

    # Moving window: slides out the first value (2.0)
    estimator.record(8.0)
    # Remaining values in window: 4.0, 6.0, 8.0 -> average = 6.0
    assert estimator.average_duration == 6.0
    assert estimator.estimate_remaining(3) == 18.0
