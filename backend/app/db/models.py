from datetime import datetime
from typing import Optional
from sqlalchemy import (
    BigInteger, Boolean, Column, DateTime, Float, ForeignKey,
    Integer, JSON, String, Text, UniqueConstraint, func
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Competition(Base):
    __tablename__ = "competitions"

    competition_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    competition_name: Mapped[str] = mapped_column(String(100), nullable=False)
    country_name: Mapped[str] = mapped_column(String(100), nullable=False)
    competition_gender: Mapped[str] = mapped_column(String(10), default="male")
    competition_youth: Mapped[bool] = mapped_column(Boolean, default=False)
    competition_international: Mapped[bool] = mapped_column(Boolean, default=False)

    seasons: Mapped[list["Season"]] = relationship(back_populates="competition")


class Season(Base):
    __tablename__ = "seasons"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    season_id: Mapped[int] = mapped_column(Integer, nullable=False)
    season_name: Mapped[str] = mapped_column(String(20), nullable=False)
    competition_id: Mapped[int] = mapped_column(ForeignKey("competitions.competition_id"))

    competition: Mapped["Competition"] = relationship(back_populates="seasons")
    matches: Mapped[list["Match"]] = relationship(back_populates="season")

    __table_args__ = (UniqueConstraint("competition_id", "season_id"),)


class Team(Base):
    __tablename__ = "teams"

    team_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    team_name: Mapped[str] = mapped_column(String(100), nullable=False)
    country_name: Mapped[Optional[str]] = mapped_column(String(100))
    team_gender: Mapped[str] = mapped_column(String(10), default="male")


class Player(Base):
    __tablename__ = "players"

    player_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    player_name: Mapped[str] = mapped_column(String(150), nullable=False)
    country_name: Mapped[Optional[str]] = mapped_column(String(100))


class Match(Base):
    __tablename__ = "matches"

    match_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    match_date: Mapped[str] = mapped_column(String(20), nullable=False)
    kick_off: Mapped[Optional[str]] = mapped_column(String(20))
    home_team_id: Mapped[int] = mapped_column(ForeignKey("teams.team_id"))
    away_team_id: Mapped[int] = mapped_column(ForeignKey("teams.team_id"))
    home_score: Mapped[int] = mapped_column(Integer, default=0)
    away_score: Mapped[int] = mapped_column(Integer, default=0)
    match_week: Mapped[Optional[int]] = mapped_column(Integer)
    stadium_name: Mapped[Optional[str]] = mapped_column(String(150))
    season_id: Mapped[int] = mapped_column(ForeignKey("seasons.id"))
    home_formation: Mapped[Optional[int]] = mapped_column(Integer)
    away_formation: Mapped[Optional[int]] = mapped_column(Integer)
    home_manager: Mapped[Optional[str]] = mapped_column(String(150))
    away_manager: Mapped[Optional[str]] = mapped_column(String(150))

    season: Mapped["Season"] = relationship(back_populates="matches")
    home_team: Mapped["Team"] = relationship(foreign_keys=[home_team_id])
    away_team: Mapped["Team"] = relationship(foreign_keys=[away_team_id])
    lineups: Mapped[list["MatchLineup"]] = relationship(back_populates="match")
    events_aggregated: Mapped[Optional["EventsAggregated"]] = relationship(
        back_populates="match", uselist=False
    )


class MatchLineup(Base):
    __tablename__ = "match_lineups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.match_id"))
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.team_id"))
    player_id: Mapped[int] = mapped_column(ForeignKey("players.player_id"))
    position_name: Mapped[Optional[str]] = mapped_column(String(50))
    jersey_number: Mapped[Optional[int]] = mapped_column(Integer)

    match: Mapped["Match"] = relationship(back_populates="lineups")
    player: Mapped["Player"] = relationship()
    team: Mapped["Team"] = relationship()

    __table_args__ = (UniqueConstraint("match_id", "player_id"),)


class EventsAggregated(Base):
    __tablename__ = "events_aggregated"

    match_id: Mapped[int] = mapped_column(
        ForeignKey("matches.match_id"), primary_key=True
    )
    total_events: Mapped[int] = mapped_column(Integer, default=0)
    total_possessions: Mapped[int] = mapped_column(Integer, default=0)
    home_shots: Mapped[int] = mapped_column(Integer, default=0)
    away_shots: Mapped[int] = mapped_column(Integer, default=0)
    home_shots_on_target: Mapped[int] = mapped_column(Integer, default=0)
    away_shots_on_target: Mapped[int] = mapped_column(Integer, default=0)
    home_passes: Mapped[int] = mapped_column(Integer, default=0)
    away_passes: Mapped[int] = mapped_column(Integer, default=0)
    home_fouls: Mapped[int] = mapped_column(Integer, default=0)
    away_fouls: Mapped[int] = mapped_column(Integer, default=0)
    key_events_json: Mapped[Optional[str]] = mapped_column(Text)

    match: Mapped["Match"] = relationship(back_populates="events_aggregated")


class AnalysisReport(Base):
    __tablename__ = "analysis_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    match_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("matches.match_id"), nullable=True
    )
    report_type: Mapped[str] = mapped_column(String(20))
    home_team_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("teams.team_id"), nullable=True
    )
    away_team_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("teams.team_id"), nullable=True
    )
    report_markdown: Mapped[str] = mapped_column(Text, nullable=False)
    user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )


class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    messages: Mapped[list[dict]] = mapped_column(JSON, nullable=False, default=list)
    qa_meta: Mapped[dict] = mapped_column(
        JSON, nullable=False, default=lambda: {"football_intent_count": 0, "generic_turn_count": 0}
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class IngestionLog(Base):
    __tablename__ = "ingestion_log"

    match_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    step_parse: Mapped[str] = mapped_column(String(10), default="pending")
    step_embed: Mapped[str] = mapped_column(String(10), default="pending")
    step_postgres: Mapped[str] = mapped_column(String(10), default="pending")
    step_redis_invalidate: Mapped[str] = mapped_column(String(10), default="pending")
    last_error: Mapped[Optional[str]] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    nickname: Mapped[str] = mapped_column(String(100), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    role: Mapped[str] = mapped_column(String(20), default="full")
    trial_expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class EmailVerificationCode(Base):
    __tablename__ = "email_verification_codes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(6), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    used: Mapped[bool] = mapped_column(Boolean, default=False)


class PasswordResetCode(Base):
    __tablename__ = "password_reset_codes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(6), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    used: Mapped[bool] = mapped_column(Boolean, default=False)
