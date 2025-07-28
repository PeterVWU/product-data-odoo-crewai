from crewai import Agent, Crew, Process, Task
from crewai.project import CrewBase, agent, crew, task
from crewai.agents.agent_builder.base_agent import BaseAgent
from typing import List
from product_data_odoo.tools.csv_processor import csv_processor_tool
from product_data_odoo.tools.product_parser import product_parser_tool
from product_data_odoo.tools.product_merger import product_merger_tool
from product_data_odoo.tools.category_mapper import category_mapper_tool
from product_data_odoo.tools.attribute_builder import attribute_builder_tool
# If you want to run a snippet of code before or after the crew starts,
# you can use the @before_kickoff and @after_kickoff decorators
# https://docs.crewai.com/concepts/crews#example-crew-class-with-decorators

@CrewBase
class ProductDataOdoo():
    """ProductDataOdoo crew"""

    agents: List[BaseAgent]
    tasks: List[Task]

    # Learn more about YAML configuration files here:
    # Agents: https://docs.crewai.com/concepts/agents#yaml-configuration-recommended
    # Tasks: https://docs.crewai.com/concepts/tasks#yaml-configuration-recommended
    
    # If you would like to add tools to your agents, you can learn more about it here:
    # https://docs.crewai.com/concepts/agents#agent-tools
    @agent
    def orchestrator(self) -> Agent:
        return Agent(
            config=self.agents_config['orchestrator'], # type: ignore[index]
            verbose=True,
            tools=[csv_processor_tool, product_parser_tool, product_merger_tool, category_mapper_tool, attribute_builder_tool],
        )

    @agent
    def smart_parser(self) -> Agent:
        return Agent(
            config=self.agents_config['smart_parser'], # type: ignore[index]
            verbose=True,
            tools=[],  # No tools needed - receives batch data directly from input
        )

    # To learn more about structured task outputs,
    # task dependencies, and task callbacks, check out the documentation:
    # https://docs.crewai.com/concepts/tasks#overview-of-a-task
    @task
    def orchestrate_task(self) -> Task:
        return Task(
            config=self.tasks_config['orchestrate_task'], # type: ignore[index]
            args={
                "encoding": "utf-8-sig",
                "error_threshold": 0.15,  # Allow up to 15% unclear products
            },
        )

    @task
    def smart_parse_task(self) -> Task:
        return Task(
            config=self.tasks_config['smart_parse_task'], # type: ignore[index]
        )

    @task
    def category_mapping_task(self) -> Task:
        return Task(
            config=self.tasks_config['category_mapping_task'], # type: ignore[index]
        )

    @task
    def attribute_building_task(self) -> Task:
        return Task(
            config=self.tasks_config['attribute_building_task'], # type: ignore[index]
        )

    @crew
    def crew(self) -> Crew:
        """Creates the ProductDataOdoo crew"""
        # To learn how to add knowledge sources to your crew, check out the documentation:
        # https://docs.crewai.com/concepts/knowledge#what-is-knowledge

        return Crew(
            agents=self.agents, # Automatically created by the @agent decorator
            tasks=self.tasks, # Automatically created by the @task decorator
            process=Process.sequential,
            verbose=True,
            # process=Process.hierarchical, # In case you wanna use that instead https://docs.crewai.com/how-to/Hierarchical/
        )
