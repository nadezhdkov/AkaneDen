"""
SkillManager — Gerenciador central de skills no padrão Shogun v3.0.

Responsável pelo ciclo de vida completo: registro, setup, invocação
com cooldown, coleta de tools, e teardown de todas as skills.

Migrado para loguru na v3.0.
"""

from __future__ import annotations

from loguru import logger

from akane_den.core.base_skill import BaseSkill


class SkillManager:
    """Gerencia o ciclo de vida de todas as skills registradas no sistema Akane."""

    def __init__(self) -> None:
        self._skills: dict[str, BaseSkill] = {}
        self._boot_order: list[str] = []

    def register(self, skill: BaseSkill) -> None:
        """Registra uma skill no manager. A ordem de registro define a ordem de boot."""
        if skill.name in self._skills:
            logger.warning(f"Skill '{skill.name}' já registrada. Substituindo, baka!")
        self._skills[skill.name] = skill
        self._boot_order.append(skill.name)
        logger.info(f"Skill registrada: {skill}")

    async def setup_all(self) -> None:
        """Executa setup() de todas as skills na ordem de registro."""
        logger.info(f"Iniciando setup de {len(self._skills)} skills...")
        for name in self._boot_order:
            skill = self._skills[name]
            try:
                await skill.setup()
                skill._active = True
                logger.success(f"  {skill.name} -- pronta.")
            except Exception as e:
                logger.error(f"  {skill.name} -- falha no setup: {e}")
                skill.context.enabled = False

        active = sum(1 for s in self._skills.values() if s.is_active)
        logger.info(f"Setup completo: {active}/{len(self._skills)} skills ativas.")

    async def invoke(self, skill_name: str, **kwargs) -> dict:
        """Invoca uma skill pelo nome, respeitando cooldowns.

        Returns:
            dict com resultados da skill, ou erro/cooldown info.
        """
        skill = self._skills.get(skill_name)
        if not skill:
            logger.warning(f"Tentativa de invocar skill inexistente: '{skill_name}'")
            return {"error": f"Skill '{skill_name}' não registrada, baka!"}

        if not skill.context.can_trigger():
            return {"cooldown": True, "skill": skill_name}

        try:
            result = await skill.execute(**kwargs)
            skill.context.mark_triggered()
            return result
        except Exception as e:
            logger.error(f"Erro ao executar skill '{skill_name}': {e}")
            return {"error": str(e), "skill": skill_name}

    def get_skill(self, name: str) -> BaseSkill | None:
        """Retorna uma skill pelo nome."""
        return self._skills.get(name)

    def get_all_tools(self) -> list:
        """Coleta LangChain tools de todas as skills ativas que expõem ferramentas."""
        tools = []
        for skill in self._skills.values():
            if skill.context.enabled and skill.is_active:
                skill_tools = skill.get_tools()
                if skill_tools:
                    tools.extend(skill_tools)
                    logger.debug(
                        f"  {skill.name} contribuiu {len(skill_tools)} tool(s)"
                    )
        return tools

    def list_skills(self) -> list[dict]:
        """Lista todas as skills e seu status."""
        return [
            {
                "name": s.name,
                "active": s.is_active,
                "enabled": s.context.enabled,
                "triggers": s.context.trigger_count,
                "class": s.__class__.__name__,
            }
            for s in self._skills.values()
        ]

    async def teardown_all(self) -> None:
        """Executa teardown() de todas as skills (ordem reversa do boot)."""
        logger.info("Iniciando teardown de todas as skills...")
        for name in reversed(self._boot_order):
            skill = self._skills[name]
            try:
                await skill.teardown()
                logger.success(f"  {skill.name} -- encerrada.")
            except Exception as e:
                logger.error(f"  {skill.name} -- erro no teardown: {e}")

    def __len__(self) -> int:
        return len(self._skills)

    def __repr__(self) -> str:
        active = sum(1 for s in self._skills.values() if s.is_active)
        return f"<SkillManager skills={len(self._skills)} active={active}>"
