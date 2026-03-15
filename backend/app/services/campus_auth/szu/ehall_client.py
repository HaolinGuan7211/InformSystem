from __future__ import annotations

import json
import re
from collections import defaultdict
from urllib.parse import parse_qs, urlparse

from backend.app.services.campus_auth.models import CampusSessionHandle

JSONP_RE = re.compile(r"^[^(]+\((?P<payload>.*)\)\s*;?\s*$", re.DOTALL)


class SzuEhallClient:
    DEFAULT_BYNJDM = "-"
    DEFAULT_PAGE_SIZE = 999

    USER_INFO_URL = "https://ehall.szu.edu.cn/jsonp/userInfo.json"
    SEND_REC_USE_APP_URL = "https://ehall.szu.edu.cn/jsonp/sendRecUseApp.json"
    XYWCFACX_URL = "https://ehall.szu.edu.cn/jwapp/sys/xywccx/modules/xsxywcck/xywcfacx.do"
    CXSCFA_URL = "https://ehall.szu.edu.cn/jwapp/sys/xywccx/modules/xywccx/cxscfa.do"
    CXSCFAKZ_URL = "https://ehall.szu.edu.cn/jwapp/sys/xywccx/modules/xywccx/cxscfakz.do"
    CXXSJBXX_URL = "https://ehall.szu.edu.cn/jwapp/sys/xywccx/modules/xywccx/cxxsjbxx.do"
    CXSCFAKZKC_URL = "https://ehall.szu.edu.cn/jwapp/sys/xywccx/modules/xywccx/cxscfakzkc.do"

    def validate_portal_session(self, handle: CampusSessionHandle) -> dict[str, object]:
        user_info = self.get_user_info(handle)
        app_id = self.extract_app_id(handle.entry_url)
        app_status = self.get_app_login_status(handle, app_id) if app_id else {}

        has_login = bool(user_info.get("hasLogin") is True or app_status.get("hasLogin") is True)
        if not has_login:
            raise PermissionError("SZU ehall session was created but portal login state is not active")

        module_probe = self.probe_academic_completion_module(handle)
        return {
            "has_login": has_login,
            "user_info": user_info,
            "app_status": app_status,
            "module_probe": module_probe,
            "app_id": app_id,
        }

    def get_user_info(self, handle: CampusSessionHandle) -> dict[str, object]:
        response = handle.session.get(
            self.USER_INFO_URL,
            timeout=20,
            headers={"Referer": handle.authenticated_url},
        )
        response.raise_for_status()
        return self._parse_json_like_payload(response.text)

    def get_app_login_status(self, handle: CampusSessionHandle, app_id: str) -> dict[str, object]:
        response = handle.session.get(
            f"{self.SEND_REC_USE_APP_URL}?appId={app_id}",
            timeout=20,
            headers={"Referer": handle.authenticated_url},
        )
        response.raise_for_status()
        return self._parse_json_like_payload(response.text)

    def probe_academic_completion_module(self, handle: CampusSessionHandle) -> dict[str, object]:
        return self.post_xywcfacx(handle)

    def post_xywcfacx(
        self,
        handle: CampusSessionHandle,
        payload: dict[str, object] | None = None,
    ) -> dict[str, object]:
        return self._post_module(handle, self.XYWCFACX_URL, payload)

    def post_cxscfa(
        self,
        handle: CampusSessionHandle,
        payload: dict[str, object] | None = None,
    ) -> dict[str, object]:
        return self._post_module(handle, self.CXSCFA_URL, payload)

    def post_cxscfakz(
        self,
        handle: CampusSessionHandle,
        payload: dict[str, object] | None = None,
    ) -> dict[str, object]:
        return self._post_module(handle, self.CXSCFAKZ_URL, payload)

    def post_cxxsjbxx(
        self,
        handle: CampusSessionHandle,
        payload: dict[str, object] | None = None,
    ) -> dict[str, object]:
        return self._post_module(handle, self.CXXSJBXX_URL, payload)

    def post_cxscfakzkc(
        self,
        handle: CampusSessionHandle,
        *,
        kzh: str,
        pyfadm: str,
        bynjdm: str = DEFAULT_BYNJDM,
        page_size: int = DEFAULT_PAGE_SIZE,
        page_number: int = 1,
        extra_payload: dict[str, object] | None = None,
    ) -> dict[str, object]:
        if not kzh.strip():
            raise ValueError("KZH is required to fetch academic completion course details")
        if not pyfadm.strip():
            raise ValueError("PYFADM is required to fetch academic completion course details")

        payload = {
            "BYNJDM": bynjdm,
            "KZH": kzh,
            "PYFADM": pyfadm,
            "pageSize": page_size,
            "pageNumber": page_number,
        }
        if extra_payload:
            payload.update(extra_payload)
        return self._post_module(handle, self.CXSCFAKZKC_URL, payload)

    def collect_academic_completion(
        self,
        handle: CampusSessionHandle,
        *,
        bynjdm: str = DEFAULT_BYNJDM,
        page_size: int = DEFAULT_PAGE_SIZE,
    ) -> dict[str, object]:
        overview_payload = self.post_xywcfacx(handle, {"BYNJDM": bynjdm}).get("payload") or {}
        overview_rows = self._extract_rows(overview_payload, "xywcfacx")
        if not overview_rows:
            raise ValueError("SZU academic completion overview did not return any rows")

        overview_row = overview_rows[0]
        pyfadm = str(overview_row.get("PYFADM") or "").strip()
        if not pyfadm:
            raise ValueError("SZU academic completion overview did not contain PYFADM")

        student_info_payload = self.post_cxxsjbxx(handle, {"BYNJDM": bynjdm}).get("payload") or {}
        student_info_rows = self._extract_rows(student_info_payload, "cxxsjbxx")

        plan_snapshot_payload = self.post_cxscfa(handle, {"BYNJDM": bynjdm}).get("payload") or {}
        plan_snapshots = self._extract_rows(plan_snapshot_payload, "cxscfa")

        node_payload = self.post_cxscfakz(handle, {"BYNJDM": bynjdm}).get("payload") or {}
        unique_nodes = self._dedupe_rows_by_key(self._extract_rows(node_payload, "cxscfakz"), "KZH")
        root_nodes = sorted(
            [node for node in unique_nodes if str(node.get("FKZH") or "").strip() == "-1"],
            key=self._node_sort_key,
        )
        child_nodes = sorted(
            [node for node in unique_nodes if str(node.get("FKZH") or "").strip() not in ("", "-1")],
            key=lambda node: (
                self._node_sort_key(next((root for root in root_nodes if root.get("KZH") == node.get("FKZH")), {})),
                self._node_sort_key(node),
            ),
        )

        root_nodes_by_kzh = {
            str(node.get("KZH")).strip(): node
            for node in root_nodes
            if str(node.get("KZH") or "").strip()
        }

        child_nodes_by_parent: dict[str, list[dict[str, object]]] = defaultdict(list)
        for node in child_nodes:
            parent_kzh = str(node.get("FKZH") or "").strip()
            if parent_kzh:
                child_nodes_by_parent[parent_kzh].append(node)

        course_groups: list[dict[str, object]] = []
        course_rows: list[dict[str, object]] = []
        for child in child_nodes:
            child_kzh = str(child.get("KZH") or "").strip()
            if not child_kzh:
                continue

            detail_payload = self.post_cxscfakzkc(
                handle,
                kzh=child_kzh,
                pyfadm=pyfadm,
                bynjdm=bynjdm,
                page_size=page_size,
            ).get("payload") or {}
            detail_dataset = self._extract_dataset(detail_payload, "cxscfakzkc")
            detail_rows = self._extract_rows(detail_payload, "cxscfakzkc")
            total_size = int(detail_dataset.get("totalSize", len(detail_rows)))
            parent_node = root_nodes_by_kzh.get(str(child.get("FKZH") or "").strip())
            course_group = {
                "parent_module": parent_node.get("KZM") if isinstance(parent_node, dict) else None,
                "parent_kzh": parent_node.get("KZH") if isinstance(parent_node, dict) else None,
                "child_module": child.get("KZM"),
                "child_kzh": child.get("KZH"),
                "required_credits": child.get("YQXF"),
                "completed_credits": child.get("WCXF"),
                "required_count": child.get("YQMS"),
                "completed_count": child.get("WCMS"),
                "course_total": total_size,
                "courses": detail_rows,
            }
            course_groups.append(course_group)

            for detail_row in detail_rows:
                enriched_row = dict(detail_row)
                enriched_row.update(
                    {
                        "parent_module": course_group["parent_module"],
                        "parent_kzh": course_group["parent_kzh"],
                        "child_module": course_group["child_module"],
                        "child_kzh": course_group["child_kzh"],
                    }
                )
                course_rows.append(enriched_row)

        root_summaries = []
        for root in root_nodes:
            root_kzh = str(root.get("KZH") or "").strip()
            child_group_items = [
                group for group in course_groups if str(group.get("parent_kzh") or "").strip() == root_kzh
            ]
            root_summaries.append(
                {
                    "root_module": root.get("KZM"),
                    "root_kzh": root.get("KZH"),
                    "children": [group["child_module"] for group in child_group_items],
                    "child_course_total": sum(int(group.get("course_total", 0)) for group in child_group_items),
                }
            )

        context = {
            "student_id": overview_row.get("XH"),
            "name": overview_row.get("XM"),
            "college": overview_row.get("SZYXDM_DISPLAY"),
            "major": overview_row.get("ZYDM_DISPLAY"),
            "grade": overview_row.get("NJDM_DISPLAY"),
            "plan_id": pyfadm,
            "plan_name": overview_row.get("PYFAMC"),
            "required_credits": overview_row.get("YQXF"),
            "completed_credits": overview_row.get("WCXF"),
            "class_name": overview_row.get("BJMC"),
        }

        return {
            "by_njdm": bynjdm,
            "context": context,
            "overview": overview_row,
            "student_info": student_info_rows[0] if student_info_rows else None,
            "plan_snapshots": plan_snapshots,
            "root_nodes": root_nodes,
            "child_nodes": child_nodes,
            "child_nodes_by_parent": {
                parent_kzh: [node.get("KZH") for node in nodes]
                for parent_kzh, nodes in child_nodes_by_parent.items()
            },
            "root_summaries": root_summaries,
            "course_groups": course_groups,
            "course_rows": course_rows,
            "summary": {
                "root_module_count": len(root_nodes),
                "child_module_count": len(child_nodes),
                "course_row_count": len(course_rows),
            },
        }

    def extract_app_id(self, entry_url: str) -> str | None:
        parsed = urlparse(entry_url)
        app_id = parse_qs(parsed.query).get("appId", [None])[0]
        return app_id

    def _parse_json_like_payload(self, text: str) -> dict[str, object]:
        stripped = text.strip()
        if not stripped:
            return {}
        try:
            return json.loads(stripped)
        except json.JSONDecodeError:
            match = JSONP_RE.match(stripped)
            if match is None:
                raise
            return json.loads(match.group("payload"))

    def _safe_parse_json_like_payload(self, text: str) -> dict[str, object] | None:
        try:
            return self._parse_json_like_payload(text)
        except json.JSONDecodeError:
            return None

    def _extract_dataset(self, payload: dict[str, object], data_key: str) -> dict[str, object]:
        datas = payload.get("datas")
        if not isinstance(datas, dict):
            return {}
        dataset = datas.get(data_key)
        return dataset if isinstance(dataset, dict) else {}

    def _extract_rows(self, payload: dict[str, object], data_key: str) -> list[dict[str, object]]:
        dataset = self._extract_dataset(payload, data_key)
        rows = dataset.get("rows")
        if not isinstance(rows, list):
            return []
        return [row for row in rows if isinstance(row, dict)]

    def _dedupe_rows_by_key(
        self,
        rows: list[dict[str, object]],
        key_name: str,
    ) -> list[dict[str, object]]:
        deduped: list[dict[str, object]] = []
        seen: set[str] = set()
        for row in rows:
            key = str(row.get(key_name) or "").strip()
            if not key or key in seen:
                continue
            seen.add(key)
            deduped.append(row)
        return deduped

    def _node_sort_key(self, node: dict[str, object]) -> tuple[str, str]:
        return (str(node.get("KZM") or "").strip(), str(node.get("KZH") or "").strip())

    def _post_module(
        self,
        handle: CampusSessionHandle,
        url: str,
        payload: dict[str, object] | None = None,
    ) -> dict[str, object]:
        response = handle.session.post(
            url,
            data=payload or {},
            timeout=20,
            headers={
                "Referer": handle.authenticated_url,
                "X-Requested-With": "XMLHttpRequest",
            },
            allow_redirects=True,
        )
        response.raise_for_status()
        final_url = response.url
        if "authserver" in final_url or "login" in final_url.lower():
            raise PermissionError(f"SZU ehall module endpoint redirected to login: {url}")
        return {
            "url": final_url,
            "status_code": response.status_code,
            "content_type": response.headers.get("content-type"),
            "payload": self._safe_parse_json_like_payload(response.text),
        }
