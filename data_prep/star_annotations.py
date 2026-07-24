"""Star annotation passes — the "most X" summary-note generators StarPipeline
runs after parsing (luminosity, brightness, proper motion, variability,
nearest, hottest, space velocity).

Split out of stars.py to keep that module under a reasonable size. Every
method here is mixed into StarPipeline via `class StarPipeline(
_StarAnnotationsMixin):` in stars.py, so each still runs with the exact same
`self` as before this split (same `self._debug`, same sibling-method calls
like `self._cap_luminosity_notes(...)`) — this is a pure move, not a rewrite.
"""

import math
import re
from typing import Any


def _lsun_str(l_sun: float) -> str:
    """Round solar luminosity to 1 significant figure and format with commas."""
    magnitude = 10 ** math.floor(math.log10(l_sun))
    return f"{int(round(l_sun / magnitude) * magnitude):,}"


class _StarAnnotationsMixin:
    """Annotation-pass methods mixed into StarPipeline (see stars.py)."""

    def _run_annotation_passes(
        self, stars: list[dict[str, Any]], var_index: dict[int, tuple] | None, top_n: int
    ) -> int:
        """Run all annotation passes; return count of stars with an auto-generated note."""
        self._safe_annotate(self._annotate_luminosity, stars, top_n)
        self._safe_annotate(self._annotate_brightness, stars, top_n)
        self._safe_annotate(self._annotate_pm, stars, top_n)
        self._safe_annotate(self._annotate_most_variable, stars, var_index or {}, top_n)
        self._safe_annotate(self._annotate_nearest, stars, top_n)
        self._safe_annotate(self._annotate_hottest, stars, top_n)
        self._safe_annotate(self._annotate_space_velocity, stars, top_n)
        # Compute the number of unique stars that received auto-generated
        # notes (marked by the helper flag set above).
        summary_ids: set[int] = {id(s) for s in stars if s.get("_auto_note")}
        return len(summary_ids)

    def _safe_annotate(self, fn: Any, *args: Any) -> None:
        try:
            fn(*args)
        except Exception:  # pylint: disable=broad-except
            if self._debug:
                raise

    def _annotate_luminosity(self, stars: list[dict[str, Any]], top_n: int) -> int:
        """Compute luminosity (L/L_sun) for stars with `mag` (float) and `dist` (pc).

        Adds temporary `_lsun` (float) and `_lsun_phrase` (str) and appends the
        phrase to `note` so that `_cap_luminosity_notes()` can trim it for all
        but the top *top_n* entries. After capping, adds a persistent note
        "Among the X stars with highest luminosity" to those top entries.
        """
        with_lsun = []
        for star in stars:
            if self._assign_lsun_to_star(star):
                with_lsun.append(star)
        if not with_lsun:
            return 0
        # Determine top N by luminosity (handle top_n > available)
        actual_top = max(0, min(top_n, len(with_lsun)))
        top_list = sorted(with_lsun, key=lambda s: s["_lsun"], reverse=True)[:actual_top]
        # Cap/remove luminosity phrases and temp fields per existing behaviour
        self._cap_luminosity_notes(stars, top_n=actual_top)
        # Add persistent summary into `smr` for the top items.
        for idx, star in enumerate(top_list, start=1):
            if idx == 1:
                summary = "The star with the highest luminosity"
            elif idx == 2:
                summary = "A star with the 2nd highest luminosity"
            elif idx == 3:
                summary = "A star with the 3rd highest luminosity"
            else:
                summary = f"Among the {actual_top} stars with highest luminosity"
            if "smr" in star and star["smr"]:
                star["smr"] = f"{star['smr']}; {summary}"
            else:
                star["smr"] = summary
            star["_auto_note"] = True
        return actual_top

    @staticmethod
    def _cap_luminosity_notes(stars: list[dict[str, Any]], top_n: int = 5) -> None:
        """Keep the luminosity phrase only for the *top_n* most luminous stars."""
        tagged = sorted(
            [s for s in stars if "_lsun" in s],
            key=lambda s: s["_lsun"],
            reverse=True,
        )
        for s in tagged[top_n:]:
            phrase = s.pop("_lsun_phrase", None)
            # Remove the phrase from the note and summary fields in all
            # common positions so only the top-N keep the luminosity claim.
            if phrase:
                smr = s.get("smr")
                if smr:
                    new = smr.replace(f"; {phrase}", "").replace(f"{phrase}; ", "")
                    new = new.replace(phrase, "")
                    new = re.sub(r"\s*;\s*", "; ", new).strip()
                    new = new.strip("; ")
                    if new:
                        s["smr"] = new
                    else:
                        s.pop("smr", None)

                note = s.get("note")
                if note:
                    newn = note.replace(f"; {phrase}", "").replace(f"{phrase}; ", "")
                    newn = newn.replace(phrase, "")
                    newn = re.sub(r"\s*;\s*", "; ", newn).strip()
                    newn = newn.strip("; ")
                    if newn:
                        s["note"] = newn
                    else:
                        s.pop("note", None)
            s.pop("_lsun", None)
        for s in tagged[:top_n]:
            s.pop("_lsun", None)
            s.pop("_lsun_phrase", None)

    def _annotate_brightness(self, stars: list[dict[str, Any]], top_n: int) -> int:
        """Mark the top *top_n* stars by apparent brightness (lowest `mag`).

        Appends a persistent summary note "Among the X brightest stars" to
        each of the selected stars and returns the actual number marked.
        """
        with_mag = [s for s in stars if isinstance(s.get("mag"), float)]
        if not with_mag:
            return 0
        actual_top = max(0, min(top_n, len(with_mag)))
        # sort by apparent magnitude (smaller = brighter)
        top_stars = sorted(with_mag, key=lambda s: s["mag"])[:actual_top]
        for idx, s in enumerate(top_stars, start=1):
            if idx == 1:
                summary = "The brightest star in the sky"
            elif idx == 2:
                summary = "The 2nd brightest star in the sky"
            elif idx == 3:
                summary = "The 3rd brightest star in the sky"
            else:
                summary = f"Among the {actual_top} brightest stars"
            if "smr" in s and s["smr"]:
                s["smr"] = f"{s['smr']}; {summary}"
            else:
                s["smr"] = summary
            s["_auto_note"] = True
        return actual_top

    def _annotate_pm(self, stars: list[dict[str, Any]], top_n: int) -> int:
        """Mark the top *top_n* stars by proper motion (pm_ra, pm_dec).

        Proper motion magnitude is computed as sqrt(pm_ra^2 + pm_dec^2)
        where the fields are expected in mas/yr. Top-ranked stars receive
        special phrasing for ranks 1..3; others receive a summary note.
        """
        with_pm = []
        for s in stars:
            pm_ra = s.get("pm_ra")
            pm_dec = s.get("pm_dec")
            if isinstance(pm_ra, (int, float)) and isinstance(pm_dec, (int, float)):
                s["_pm"] = float(math.hypot(pm_ra, pm_dec))
                with_pm.append(s)
        if not with_pm:
            return 0
        actual_top = max(0, min(top_n, len(with_pm)))
        top_list = sorted(with_pm, key=lambda s: s["_pm"], reverse=True)[:actual_top]

        def _fmt_arcsec_per_year(pm_masyr: float) -> str:
            # mas/yr -> arcsec/yr: arcsec = pm_masyr / 1000
            arcsec = pm_masyr / 1000.0
            # Format with 2 decimal places for readability
            return f"{arcsec:.2f}\"/yr"

        for idx, s in enumerate(top_list, start=1):
            if idx == 1:
                summary = "The star with the highest proper motion"
            elif idx == 2:
                summary = "The star with the 2nd highest proper motion"
            elif idx == 3:
                summary = "The star with the 3rd highest proper motion"
            else:
                summary = f"Among the {actual_top} stars with highest proper motion"
            # append a human-readable proper-motion rate (arcsec per year)
            pm_val = s.get("_pm")
            if isinstance(pm_val, (int, float)):
                pm_str = _fmt_arcsec_per_year(pm_val)
                summary = f"{summary} - {pm_str}"
            if "smr" in s and s["smr"]:
                s["smr"] = f"{s['smr']}; {summary}"
            else:
                s["smr"] = summary
            s["_auto_note"] = True
        return actual_top

    @staticmethod
    def _collect_variable_amplitudes(
        stars: list[dict[str, Any]],
        var_index: dict[int, tuple],
    ) -> list[tuple[dict[str, Any], float]]:
        result: list[tuple[dict[str, Any], float]] = []
        for s in stars:
            hip = s.get("hip")
            if hip and hip in var_index:
                rng = var_index[hip]
                if rng and isinstance(rng[0], (int, float)) and isinstance(rng[1], (int, float)):
                    amp = rng[1] - rng[0]
                    if amp > 0:
                        result.append((s, amp))
        return result

    def _annotate_most_variable(
        self,
        stars: list[dict[str, Any]],
        var_index: dict[int, tuple] | None,
        top_n: int,
    ) -> int:
        """Mark the top *top_n* stars by variability amplitude from *var_index*.

        *var_index* is a HIP -> (min_mag, max_mag, var_type, period) mapping.
        """
        if not var_index:
            return 0
        var_list = self._collect_variable_amplitudes(stars, var_index)
        if not var_list:
            return 0
        var_list.sort(key=lambda x: x[1], reverse=True)
        actual_top = max(0, min(top_n, len(var_list)))
        for idx, (s, amp) in enumerate(var_list[:actual_top], start=1):
            if idx == 1:
                summary = f"The most variable star (amplitude {amp:.2f} mag)"
            elif idx == 2:
                summary = f"The 2nd most variable star (amplitude {amp:.2f} mag)"
            elif idx == 3:
                summary = f"The 3rd most variable star (amplitude {amp:.2f} mag)"
            else:
                summary = f"Among the {actual_top} most variable stars (amplitude {amp:.2f} mag)"
            if "smr" in s and s["smr"]:
                s["smr"] = f"{s['smr']}; {summary}"
            else:
                s["smr"] = summary
            s["_auto_note"] = True
        return actual_top

    def _annotate_nearest(self, stars: list[dict[str, Any]], top_n: int) -> int:
        """Mark the top *top_n* nearest stars (showing distance in ly)."""
        with_dist = [
            s
            for s in stars
            if isinstance(s.get("dist"), (int, float)) and s.get("dist") > 0
        ]
        if not with_dist:
            return 0
        with_dist.sort(key=lambda s: s["dist"])  # ascending pc
        actual_top = max(0, min(top_n, len(with_dist)))
        for idx, s in enumerate(with_dist[:actual_top], start=1):
            ly = s["dist"] * 3.26156
            if idx == 1:
                summary = f"The nearest star — {ly:.2f} ly"
            elif idx == 2:
                summary = f"The 2nd nearest star — {ly:.2f} ly"
            elif idx == 3:
                summary = f"The 3rd nearest star — {ly:.2f} ly"
            else:
                summary = f"Among the {actual_top} nearest stars — {ly:.2f} ly"
            if "smr" in s and s["smr"]:
                s["smr"] = f"{s['smr']}; {summary}"
            else:
                s["smr"] = summary
            s["_auto_note"] = True
        return actual_top

    def _annotate_hottest(self, stars: list[dict[str, Any]], top_n: int) -> int:
        """Rank by Harvard spectral class (O hottest → M coolest)."""
        order = {"O": 0, "B": 1, "A": 2, "F": 3, "G": 4, "K": 5, "M": 6, "W": 7, "C": 8, "S": 9}
        parsed: list[tuple[dict[str, Any], int, float]] = []
        for s in stars:
            spect = s.get("spect") or ""
            if not spect:
                continue
            m = re.match(r"^([OBAFGKMWCS])([0-9.]*)", spect.strip(), re.I)
            if not m:
                continue
            letter = m.group(1).upper()
            subtype = float(m.group(2)) if m.group(2) else 5.0
            rank_key = order.get(letter, 99)
            parsed.append((s, rank_key, subtype))
        if not parsed:
            return 0
        parsed.sort(key=lambda x: (x[1], x[2]))
        actual_top = max(0, min(top_n, len(parsed)))
        for idx, (s, _, _) in enumerate(parsed[:actual_top], start=1):
            if idx == 1:
                summary = "The hottest star"
            elif idx == 2:
                summary = "The 2nd hottest star"
            elif idx == 3:
                summary = "The 3rd hottest star"
            else:
                summary = f"Among the {actual_top} hottest stars"
            if "smr" in s and s["smr"]:
                s["smr"] = f"{s['smr']}; {summary}"
            else:
                s["smr"] = summary
            s["_auto_note"] = True
        return actual_top

    def _assign_lsun_to_star(self, star: dict[str, Any]) -> bool:
        """Compute and attach luminosity fields for *star*.

        Returns True if luminosity was computed and attached, False otherwise.
        """
        m_sun = 4.83
        mag = star.get("mag")
        dist = star.get("dist")
        if not (isinstance(mag, float) and isinstance(dist, (int, float)) and dist and dist > 0):
            return False
        try:
            abs_mag = mag - 5 * math.log10(dist / 10)
            lsun = 10 ** ((m_sun - abs_mag) / 2.5)
        except (ValueError, OverflowError):
            return False
        star["_lsun"] = float(lsun)
        phrase = f"~{_lsun_str(lsun)}× the Sun's luminosity"
        star["_lsun_phrase"] = phrase
        # Auto-generated phrases go into the `smr` (summary) field. Always
        # attach the luminosity phrase to `smr` so curated `note` remains
        # untouched while still recording autogenerated summaries.
        if "smr" in star and star["smr"]:
            star["smr"] = f"{star['smr']}; {phrase}"
        else:
            star["smr"] = phrase
        return True

    @staticmethod
    def _compute_space_velocity(s: dict[str, Any]) -> float | None:
        pm_ra = s.get("pm_ra")
        pm_dec = s.get("pm_dec")
        dist = s.get("dist")
        if not (
            isinstance(pm_ra, (int, float))
            and isinstance(pm_dec, (int, float))
            and isinstance(dist, (int, float))
            and dist > 0
        ):
            return None
        mu_masyr = math.hypot(pm_ra, pm_dec)
        mu_arcsec = mu_masyr / 1000.0
        vt = 4.74047 * mu_arcsec * dist
        rv = s.get("rv")
        if isinstance(rv, (int, float)):
            return math.hypot(vt, rv)
        return vt

    def _annotate_space_velocity(self, stars: list[dict[str, Any]], top_n: int) -> int:
        """Annotate stars with highest total space velocity (km/s).

        Uses `pm_ra`, `pm_dec` (mas/yr), `dist` (pc) and optional `rv` (km/s).
        Ranks by total velocity sqrt(vt^2 + rv^2) when RV present, else by vt.
        Notes only include the total km/s rounded to 1 decimal place.
        """
        vals: list[tuple[dict[str, Any], float]] = []
        for s in stars:
            vtot = self._compute_space_velocity(s)
            if vtot is not None:
                vals.append((s, vtot))
        if not vals:
            return 0
        vals.sort(key=lambda x: x[1], reverse=True)
        actual_top = max(0, min(top_n, len(vals)))
        for idx, (s, vtot) in enumerate(vals[:actual_top], start=1):
            if idx == 1:
                summary = f"The star with the highest total space velocity — {vtot:.1f} km/s"
            elif idx == 2:
                summary = f"The star with the 2nd highest total space velocity — {vtot:.1f} km/s"
            elif idx == 3:
                summary = f"The star with the 3rd highest total space velocity — {vtot:.1f} km/s"
            else:
                summary = (
                    f"Among the {actual_top} stars with highest total space velocity — "
                    f"{vtot:.1f} km/s"
                )
            if "smr" in s and s["smr"]:
                s["smr"] = f"{s['smr']}; {summary}"
            else:
                s["smr"] = summary
            s["_auto_note"] = True
        return actual_top
