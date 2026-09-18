"""Chart generation for the Student Grade Analyzer.

Reproduces the four images V1 generated (bar, pie, radar and the
combined dashboard), reusing the same low-level drawing helpers so a
chart looks the same whether it is saved alone or drawn in the dashboard.
"""

import numpy as np
import matplotlib.pyplot as plt

from grade_analyzer import config
from grade_analyzer.analysis import build_summary_text


def _names_and_marks(subjects):
    """Return (subject_names, marks) in the same order as the subjects."""
    return (
        [subject.name for subject in subjects],
        [subject.mark for subject in subjects],
    )


def _radar_data(subjects):
    """Return the data needed to draw a closed radar chart.

    The angles spread evenly around the circle and the marks are
    extended with a copy of the first mark so the loop is closed.
    """
    names, marks = _names_and_marks(subjects)

    angles = np.linspace(0, 2 * np.pi, len(subjects), endpoint=False)

    radar_marks = marks + [marks[0]]
    radar_angles = list(angles) + [angles[0]]

    return names, marks, angles, radar_marks, radar_angles


def _draw_bar_plot(ax, names, marks, title, ylabel, tick_ha=None):
    """Draw a styled bar chart on an axis (shared by dashboard and standalone)."""
    bars = ax.bar(names, marks)

    ax.set_title(title)
    ax.set_ylabel(ylabel)
    ax.set_ylim(0, 100)

    ax.tick_params(axis="x", rotation=25)

    if tick_ha:
        for label in ax.get_xticklabels():
            label.set_ha(tick_ha)

    for bar, mark in zip(bars, marks):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + 2,
            f"{mark:.0f}%",
            ha="center",
        )


def _draw_radar_plot(ax, names, angles, radar_marks, radar_angles, title):
    """Draw a styled radar chart on an axis (shared by dashboard and standalone)."""
    ax.plot(radar_angles, radar_marks, linewidth=2)

    ax.fill(radar_angles, radar_marks, alpha=0.25)

    ax.set_xticks(angles)
    ax.set_xticklabels(names)

    ax.set_ylim(0, 100)

    ax.set_title(title, pad=20)


def save_bar_chart(subjects, output_dir=config.OUTPUT_DIR):
    """Save the standalone bar chart, identical to V1.

    Returns the path of the created image.
    """
    names, marks = _names_and_marks(subjects)

    fig = plt.figure(figsize=(10, 6))

    ax = fig.add_subplot(111)

    _draw_bar_plot(
        ax,
        names,
        marks,
        config.BAR_CHART_TITLE,
        "Marks (%)",
        tick_ha="right",
    )
    ax.set_xlabel("Subjects")

    plt.tight_layout()

    chart_path = output_dir / config.BAR_CHART_FILENAME

    fig.savefig(chart_path, dpi=config.CHART_DPI)

    plt.close(fig)

    return chart_path


def save_pie_chart(subjects, output_dir=config.OUTPUT_DIR):
    """Save the standalone pie chart, identical to V1.

    Returns the path of the created image.
    """
    names, marks = _names_and_marks(subjects)

    fig = plt.figure(figsize=(8, 8))

    ax = fig.add_subplot(111)

    ax.pie(
        marks,
        labels=names,
        autopct="%1.1f%%",
        startangle=90,
    )

    ax.set_title(config.PIE_CHART_TITLE)

    plt.tight_layout()

    chart_path = output_dir / config.PIE_CHART_FILENAME

    fig.savefig(chart_path, dpi=config.CHART_DPI)

    plt.close(fig)

    return chart_path


def save_radar_chart(subjects, output_dir=config.OUTPUT_DIR):
    """Save the standalone radar chart, identical to V1.

    Returns the path of the created image.
    """
    names, marks, angles, radar_marks, radar_angles = _radar_data(subjects)

    fig = plt.figure(figsize=(8, 8))

    ax = fig.add_subplot(111, polar=True)

    _draw_radar_plot(
        ax,
        names,
        angles,
        radar_marks,
        radar_angles,
        config.RADAR_CHART_TITLE,
    )

    plt.tight_layout()

    chart_path = output_dir / config.RADAR_CHART_FILENAME

    fig.savefig(chart_path, dpi=config.CHART_DPI, bbox_inches="tight")

    plt.close(fig)

    return chart_path


def save_dashboard(result, output_dir=config.OUTPUT_DIR):
    """Save the combined 4-panel dashboard, identical to V1.

    Uses the shared drawing helpers, so the panels look exactly like the
    standalone charts.  Returns the path of the created image.
    """
    names, marks = _names_and_marks(result.subjects)

    _, _, angles, radar_marks, radar_angles = _radar_data(result.subjects)

    fig = plt.figure(figsize=(16, 10))

    fig.suptitle(
        f"{result.student_name} - {config.DEPARTMENT_TITLE} Performance",
        fontsize=20,
        fontweight="bold",
    )

    # ---------- BAR CHART ----------
    ax1 = plt.subplot(2, 2, 1)

    _draw_bar_plot(ax1, names, marks, "Subject Performance", "Percentage")

    # ---------- PIE CHART ----------
    ax2 = plt.subplot(2, 2, 2)

    ax2.pie(
        marks,
        labels=names,
        autopct="%1.1f%%",
        startangle=90,
    )

    ax2.set_title("Marks Distribution")

    # ---------- RADAR CHART ----------
    ax3 = plt.subplot(2, 2, 3, polar=True)

    _draw_radar_plot(
        ax3,
        names,
        angles,
        radar_marks,
        radar_angles,
        "Performance Radar",
    )

    # ---------- SUMMARY ----------
    ax4 = plt.subplot(2, 2, 4)

    ax4.axis("off")

    ax4.text(
        0.1,
        0.9,
        build_summary_text(result),
        fontsize=13,
        verticalalignment="top",
    )

    dashboard_path = output_dir / config.DASHBOARD_FILENAME

    plt.tight_layout()

    fig.savefig(dashboard_path, dpi=config.CHART_DPI, bbox_inches="tight")

    plt.close(fig)

    return dashboard_path