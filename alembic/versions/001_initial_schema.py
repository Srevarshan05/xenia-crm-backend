"""Create all Xenia CRM tables

Revision ID: 001_initial
Revises: 
Create Date: 2026-06-11 00:00:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Enable uuid-ossp extension
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')

    # ── customers ──────────────────────────────────────────────────────────────
    op.create_table(
        "customers",
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("phone", sa.String(20)),
        sa.Column("city", sa.String(100)),
        sa.Column("join_date", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_customers_email", "customers", ["email"])
    op.create_index("ix_customers_city", "customers", ["city"])

    # ── products ───────────────────────────────────────────────────────────────
    op.create_table(
        "products",
        sa.Column("product_id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("name", sa.String(300), nullable=False),
        sa.Column("category", sa.String(100), nullable=False),
        sa.Column("price", sa.Numeric(10, 2), nullable=False),
        sa.Column("brand", sa.String(200)),
        sa.Column("sku", sa.String(100), unique=True),
    )
    op.create_index("ix_products_category", "products", ["category"])
    op.create_index("ix_products_name", "products", ["name"])

    # ── promotions ─────────────────────────────────────────────────────────────
    op.create_table(
        "promotions",
        sa.Column("promotion_id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("name", sa.String(300), nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("category", sa.String(100)),
        sa.Column("discount_percentage", sa.Numeric(5, 2), nullable=False),
        sa.Column("min_order_value", sa.Numeric(10, 2)),
        sa.Column("active", sa.Boolean, server_default="true"),
        sa.Column("promo_code", sa.String(50), unique=True),
    )
    op.create_index("ix_promotions_category", "promotions", ["category"])
    op.create_index("ix_promotions_active", "promotions", ["active"])

    # ── opportunities ──────────────────────────────────────────────────────────
    op.create_table(
        "opportunities",
        sa.Column("opportunity_id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("type", sa.String(100), nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("audience_size", sa.Integer),
        sa.Column("segment_filter", postgresql.JSONB),
        sa.Column("customer_ids_sample", postgresql.JSONB),
        sa.Column("potential_revenue", sa.Numeric(14, 2)),
        sa.Column("priority", sa.String(20), server_default="medium"),
        sa.Column("ai_explanation", sa.Text),
        sa.Column("ai_action_plan", sa.Text),
        sa.Column("ai_context", postgresql.JSONB),
        sa.Column("confidence_score", sa.Float),
        sa.Column("key_drivers", postgresql.JSONB),
        sa.Column("recommended_promotion_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("promotions.promotion_id", ondelete="SET NULL"), nullable=True),
        sa.Column("recommended_channel", sa.String(50)),
        sa.Column("status", sa.String(50), server_default="open"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_opportunities_type", "opportunities", ["type"])
    op.create_index("ix_opportunities_priority", "opportunities", ["priority"])
    op.create_index("ix_opportunities_status", "opportunities", ["status"])

    # ── campaigns ──────────────────────────────────────────────────────────────
    op.create_table(
        "campaigns",
        sa.Column("campaign_id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("name", sa.String(300), nullable=False),
        sa.Column("objective", sa.Text),
        sa.Column("promotion_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("promotions.promotion_id", ondelete="SET NULL"), nullable=True),
        sa.Column("channel", sa.String(50), nullable=False),
        sa.Column("status", sa.String(50), server_default="draft"),
        sa.Column("ai_strategy", postgresql.JSONB),
        sa.Column("message_template", sa.Text),
        sa.Column("message_variants", postgresql.JSONB),
        sa.Column("target_segment", sa.String(200)),
        sa.Column("target_audience_size", sa.Integer),
        sa.Column("opportunity_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("opportunities.opportunity_id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("launched_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_campaigns_status", "campaigns", ["status"])

    # ── communications ─────────────────────────────────────────────────────────
    op.create_table(
        "communications",
        sa.Column("communication_id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("campaign_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("campaigns.campaign_id", ondelete="CASCADE"), nullable=False),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("customers.customer_id", ondelete="CASCADE"), nullable=False),
        sa.Column("channel", sa.String(50)),
        sa.Column("message_sent", sa.Text),
        sa.Column("status", sa.String(50), server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_communications_campaign_id", "communications", ["campaign_id"])
    op.create_index("ix_communications_customer_id", "communications", ["customer_id"])
    op.create_index("ix_communications_status", "communications", ["status"])

    # ── orders (after communications for FK) ───────────────────────────────────
    op.create_table(
        "orders",
        sa.Column("order_id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("customers.customer_id", ondelete="CASCADE"), nullable=False),
        sa.Column("order_date", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("total_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("attributed_communication_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("communications.communication_id", ondelete="SET NULL"), nullable=True),
    )
    op.create_index("ix_orders_customer_id", "orders", ["customer_id"])
    op.create_index("ix_orders_order_date", "orders", ["order_date"])
    op.create_index("ix_orders_attributed_communication_id", "orders", ["attributed_communication_id"])

    # ── order_items ────────────────────────────────────────────────────────────
    op.create_table(
        "order_items",
        sa.Column("order_item_id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("order_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("orders.order_id", ondelete="CASCADE"), nullable=False),
        sa.Column("product_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("products.product_id", ondelete="RESTRICT"), nullable=False),
        sa.Column("quantity", sa.Integer, nullable=False, server_default="1"),
        sa.Column("unit_price", sa.Numeric(10, 2), nullable=False),
    )
    op.create_index("ix_order_items_order_id", "order_items", ["order_id"])

    # ── communication_events ───────────────────────────────────────────────────
    op.create_table(
        "communication_events",
        sa.Column("event_id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("communication_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("communications.communication_id", ondelete="CASCADE"), nullable=False),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("event_timestamp", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("metadata_json", postgresql.JSONB),
    )
    op.create_index("ix_communication_events_communication_id", "communication_events", ["communication_id"])
    op.create_index("ix_communication_events_event_type", "communication_events", ["event_type"])

    # ── customer_metrics ───────────────────────────────────────────────────────
    op.create_table(
        "customer_metrics",
        sa.Column("customer_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("customers.customer_id", ondelete="CASCADE"), primary_key=True),
        sa.Column("r_score", sa.Integer),
        sa.Column("f_score", sa.Integer),
        sa.Column("m_score", sa.Integer),
        sa.Column("value_score", sa.Float),
        sa.Column("churn_score", sa.Float),
        sa.Column("churn_probability", sa.Float),
        sa.Column("engagement_score", sa.Float),
        sa.Column("preferred_channel", sa.String(50)),
        sa.Column("top_category", sa.String(100)),
        sa.Column("category_affinity_json", postgresql.JSONB),
        sa.Column("total_orders", sa.Integer),
        sa.Column("total_spend", sa.Float),
        sa.Column("avg_order_value", sa.Float),
        sa.Column("days_since_last_order", sa.Integer),
        sa.Column("orders_last_90d", sa.Integer),
        sa.Column("orders_prev_90d", sa.Integer),
        sa.Column("last_updated", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_customer_metrics_churn", "customer_metrics", ["churn_probability"])
    op.create_index("ix_customer_metrics_value", "customer_metrics", ["value_score"])

    # ── customer_segments ──────────────────────────────────────────────────────
    op.create_table(
        "customer_segments",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("customers.customer_id", ondelete="CASCADE"), nullable=False),
        sa.Column("segment_name", sa.String(100), nullable=False),
        sa.Column("assigned_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_customer_segment_unique", "customer_segments", ["customer_id", "segment_name"], unique=True)
    op.create_index("ix_customer_segments_segment_name", "customer_segments", ["segment_name"])

    # ── customer_insights ──────────────────────────────────────────────────────
    op.create_table(
        "customer_insights",
        sa.Column("customer_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("customers.customer_id", ondelete="CASCADE"), primary_key=True),
        sa.Column("ai_persona", sa.String(100)),
        sa.Column("persona_description", sa.Text),
        sa.Column("summary", sa.Text),
        sa.Column("risks", postgresql.JSONB),
        sa.Column("recommendations", postgresql.JSONB),
        sa.Column("confidence_score", sa.Float),
        sa.Column("model_version", sa.String(50)),
        sa.Column("last_updated", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── campaign_simulations ───────────────────────────────────────────────────
    op.create_table(
        "campaign_simulations",
        sa.Column("simulation_id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("campaign_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("campaigns.campaign_id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("predicted_reach", sa.Integer),
        sa.Column("predicted_ctr", sa.Float),
        sa.Column("predicted_cvr", sa.Float),
        sa.Column("predicted_revenue", sa.Numeric(14, 2)),
        sa.Column("confidence_score", sa.Float),
        sa.Column("risk_factors", postgresql.JSONB),
        sa.Column("simulation_context", postgresql.JSONB),
        sa.Column("ai_narrative", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── campaign_metrics ───────────────────────────────────────────────────────
    op.create_table(
        "campaign_metrics",
        sa.Column("campaign_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("campaigns.campaign_id", ondelete="CASCADE"), primary_key=True),
        sa.Column("total_sent", sa.Integer, server_default="0"),
        sa.Column("total_delivered", sa.Integer, server_default="0"),
        sa.Column("total_opened", sa.Integer, server_default="0"),
        sa.Column("total_clicked", sa.Integer, server_default="0"),
        sa.Column("total_purchased", sa.Integer, server_default="0"),
        sa.Column("total_failed", sa.Integer, server_default="0"),
        sa.Column("attributed_revenue", sa.Numeric(14, 2), server_default="0"),
        sa.Column("estimated_cost", sa.Numeric(14, 2), server_default="0"),
        sa.Column("roi", sa.Float),
        sa.Column("conversion_rate", sa.Float),
        sa.Column("last_updated", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── daily_briefings ────────────────────────────────────────────────────────
    op.create_table(
        "daily_briefings",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("briefing_date", sa.Date, nullable=False, unique=True),
        sa.Column("headline", sa.Text),
        sa.Column("summary", sa.Text),
        sa.Column("opportunities_count", sa.Integer, server_default="0"),
        sa.Column("at_risk_count", sa.Integer, server_default="0"),
        sa.Column("recoverable_revenue", sa.Numeric(14, 2)),
        sa.Column("full_content", postgresql.JSONB),
        sa.Column("confidence_score", sa.Float),
        sa.Column("model_version", sa.String(50)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_daily_briefings_date", "daily_briefings", ["briefing_date"])

    # ── nl_queries ─────────────────────────────────────────────────────────────
    op.create_table(
        "nl_queries",
        sa.Column("query_id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("question", sa.Text, nullable=False),
        sa.Column("intent", sa.String(100)),
        sa.Column("context_json", postgresql.JSONB),
        sa.Column("response", sa.Text),
        sa.Column("data_points", postgresql.JSONB),
        sa.Column("chart_suggestion", sa.String(100)),
        sa.Column("confidence_score", sa.Float),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_nl_queries_intent", "nl_queries", ["intent"])
    op.create_index("ix_nl_queries_created_at", "nl_queries", ["created_at"])


def downgrade() -> None:
    op.drop_table("nl_queries")
    op.drop_table("daily_briefings")
    op.drop_table("campaign_metrics")
    op.drop_table("campaign_simulations")
    op.drop_table("customer_insights")
    op.drop_table("customer_segments")
    op.drop_table("customer_metrics")
    op.drop_table("communication_events")
    op.drop_table("order_items")
    op.drop_table("orders")
    op.drop_table("communications")
    op.drop_table("campaigns")
    op.drop_table("opportunities")
    op.drop_table("promotions")
    op.drop_table("products")
    op.drop_table("customers")
