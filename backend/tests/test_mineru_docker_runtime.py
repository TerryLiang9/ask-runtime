from pathlib import Path
import unittest


class MineruDockerRuntimeConfigTestCase(unittest.TestCase):
    def test_docker_runtime_pins_model_tree_hash_inputs(self) -> None:
        repo_root = Path(__file__).resolve().parents[2]
        dockerfile = (repo_root / "backend" / "Dockerfile").read_text(encoding="utf-8")
        install_script = (repo_root / "backend" / "scripts" / "install-mineru-runtime.sh").read_text(encoding="utf-8")
        compose_file = (repo_root / "docker-compose.yml").read_text(encoding="utf-8")
        env_example = (repo_root / ".env.example").read_text(encoding="utf-8")

        self.assertIn("MINERU_BUILD_MODEL_TREE_SHA256", install_script)
        self.assertIn("MINERU_BUILD_MODEL_TREE_SHA256", compose_file)
        self.assertIn("EMATA_MINERU_DOCKER_MODEL_TREE_SHA256", env_example)
        self.assertIn("/usr/local/bin/mineru", dockerfile)

    def test_default_docker_runtime_does_not_point_to_uninstalled_mineru_path(self) -> None:
        repo_root = Path(__file__).resolve().parents[2]
        compose_file = (repo_root / "docker-compose.yml").read_text(encoding="utf-8")

        self.assertIn('INSTALL_MINERU_RUNTIME: "${EMATA_INSTALL_MINERU_RUNTIME:-false}"', compose_file)
        self.assertIn('EMATA_MINERU_EXECUTABLE: "${EMATA_MINERU_EXECUTABLE:-mineru}"', compose_file)
        self.assertNotIn("EMATA_MINERU_EXECUTABLE: /opt/mineru-runtime/bin/mineru", compose_file)

    def test_backend_image_installs_node_runtime_for_lark_cli_npx_fallback(self) -> None:
        repo_root = Path(__file__).resolve().parents[2]
        dockerfile = (repo_root / "backend" / "Dockerfile").read_text(encoding="utf-8")

        self.assertIn("FROM node:22-bookworm-slim AS node-runtime", dockerfile)
        self.assertIn("COPY --from=node-runtime /usr/local/bin/node", dockerfile)
        self.assertIn("EMATA_LARK_CLI_EXECUTABLE", dockerfile)

    def test_compose_waits_for_stateful_dependency_health(self) -> None:
        repo_root = Path(__file__).resolve().parents[2]
        compose_file = (repo_root / "docker-compose.yml").read_text(encoding="utf-8")

        self.assertIn("condition: service_healthy", compose_file)
        self.assertIn("pg_isready -U emata -d emata", compose_file)
        self.assertIn("redis-cli ping", compose_file)
        self.assertIn("healthz", compose_file)


if __name__ == "__main__":
    unittest.main()
