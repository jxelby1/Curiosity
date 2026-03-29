from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
API_CLIENT = ROOT / 'frontend' / 'lib' / 'api.ts'
NOTES_PAGE = ROOT / 'frontend' / 'app' / 'topics' / '[topicId]' / 'notes' / 'page.tsx'
SKILL_PAGE = ROOT / 'frontend' / 'app' / 'topics' / '[topicId]' / 'skills' / '[skillId]' / 'page.tsx'
ROUTES_FILE = ROOT / 'backend' / 'app' / 'api' / 'routes.py'


def test_frontend_fetches_proof_artifacts_with_authenticated_blob_requests() -> None:
    content = API_CLIENT.read_text(encoding='utf-8')
    assert 'async function requestBlob(' in content
    assert "headers.set('Authorization', `Bearer ${token}`);" in content
    assert 'export async function fetchProtectedBlob(pathOrUrl: string): Promise<Blob>' in content


def test_notes_and_skill_views_use_authenticated_artifact_viewer() -> None:
    notes_content = NOTES_PAGE.read_text(encoding='utf-8')
    skill_content = SKILL_PAGE.read_text(encoding='utf-8')
    assert "import { ProofArtifactViewer } from '@/components/proof-artifact-viewer';" in notes_content
    assert "import { ProofArtifactViewer } from '@/components/proof-artifact-viewer';" in skill_content
    assert '<ProofArtifactViewer proofUrl={String(entry.metadata.proof_url)} />' in notes_content
    assert '<ProofArtifactViewer proofUrl={proofHref} showPreview={false} />' in skill_content


def test_backend_proof_endpoint_remains_user_scoped() -> None:
    content = ROUTES_FILE.read_text(encoding='utf-8')
    assert "@router.get('/exercise-completions/{completion_id}/proof')" in content
    assert 'ExerciseCompletion.user_id == current_user.id' in content
