interface IRelationships {
  hostiles?: { [sideId: string]: string[] };
  allies?: { [sideId: string]: string[] };
}

export default class Relationships {
  hostiles: { [sideId: string]: string[] };
  allies: { [sideId: string]: string[] };

  constructor(parameters: IRelationships) {
    this.hostiles = parameters.hostiles ?? {};
    this.allies = parameters.allies ?? {};
  }

  private _addHostileOneWay(sideId: string, hostileId: string) {
    if (!this.hostiles[sideId]) {
      this.hostiles[sideId] = [];
    }
    if (!this.hostiles[sideId].includes(hostileId)) {
      this.hostiles[sideId].push(hostileId);
    }
    if (this.allies[sideId]) {
      this.allies[sideId] = this.allies[sideId].filter(
        (id) => id !== hostileId
      );
    }
  }

  private _removeHostileOneWay(sideId: string, hostileId: string) {
    if (this.hostiles[sideId]) {
      this.hostiles[sideId] = this.hostiles[sideId].filter(
        (id) => id !== hostileId
      );
    }
  }

  private _addAllyOneWay(sideId: string, allyId: string) {
    if (!this.allies[sideId]) {
      this.allies[sideId] = [];
    }
    if (!this.allies[sideId].includes(allyId)) {
      this.allies[sideId].push(allyId);
    }
    if (this.hostiles[sideId]) {
      this.hostiles[sideId] = this.hostiles[sideId].filter(
        (id) => id !== allyId
      );
    }
  }

  private _removeAllyOneWay(sideId: string, allyId: string) {
    if (this.allies[sideId]) {
      this.allies[sideId] = this.allies[sideId].filter((id) => id !== allyId);
    }
  }

  addHostile(sideId: string, hostileId: string) {
    if (sideId === hostileId) return;
    this._addHostileOneWay(sideId, hostileId);
    this._addHostileOneWay(hostileId, sideId);
  }

  removeHostile(sideId: string, hostileId: string) {
    this._removeHostileOneWay(sideId, hostileId);
    this._removeHostileOneWay(hostileId, sideId);
  }

  addAlly(sideId: string, allyId: string) {
    if (sideId === allyId) return;
    this._addAllyOneWay(sideId, allyId);
    this._addAllyOneWay(allyId, sideId);
  }

  removeAlly(sideId: string, allyId: string) {
    this._removeAllyOneWay(sideId, allyId);
    this._removeAllyOneWay(allyId, sideId);
  }

  isAlly(sideId: string, allyId: string): boolean {
    return this.allies[sideId]?.includes(allyId) ?? false;
  }

  isHostile(sideId: string, hostileId: string): boolean {
    return this.hostiles[sideId]?.includes(hostileId) ?? false;
  }

  getAllies(sideId: string): string[] {
    return this.allies[sideId] ?? [];
  }

  getHostiles(sideId: string): string[] {
    return this.hostiles[sideId] ?? [];
  }

  updateRelationship(sideId: string, hostiles: string[], allies: string[]) {
    const nextHostiles = Array.from(
      new Set(hostiles.filter((id) => id && id !== sideId))
    );
    const nextAllies = Array.from(
      new Set(
        allies.filter(
          (id) => id && id !== sideId && !nextHostiles.includes(id)
        )
      )
    );
    const prevHostiles = this.hostiles[sideId] ?? [];
    const prevAllies = this.allies[sideId] ?? [];

    this.hostiles[sideId] = nextHostiles;
    this.allies[sideId] = nextAllies;

    const addedHostiles = nextHostiles.filter(
      (id) => !prevHostiles.includes(id)
    );
    const removedHostiles = prevHostiles.filter(
      (id) => !nextHostiles.includes(id)
    );
    const addedAllies = nextAllies.filter((id) => !prevAllies.includes(id));
    const removedAllies = prevAllies.filter((id) => !nextAllies.includes(id));

    addedHostiles.forEach((otherId) =>
      this._addHostileOneWay(otherId, sideId)
    );
    removedHostiles.forEach((otherId) =>
      this._removeHostileOneWay(otherId, sideId)
    );
    addedAllies.forEach((otherId) => this._addAllyOneWay(otherId, sideId));
    removedAllies.forEach((otherId) =>
      this._removeAllyOneWay(otherId, sideId)
    );
  }

  deleteSide(sideId: string) {
    Object.keys(this.hostiles).forEach((key) => {
      this.hostiles[key] = this.hostiles[key].filter((id) => id !== sideId);
    });
    Object.keys(this.allies).forEach((key) => {
      this.allies[key] = this.allies[key].filter((id) => id !== sideId);
    });
    delete this.hostiles[sideId];
    delete this.allies[sideId];
  }
}
